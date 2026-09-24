"""Document ingestion: upload, background processing, reprocess, delete.

Processing runs off the request thread via a small TaskQueue indirection. The
default implementation uses FastAPI BackgroundTasks; swapping in Celery/Redis
means implementing `submit` and pointing `task_queue` at it -- no router or
service code changes.
"""

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.rag.chunker import chunk_pages
from app.rag.embedder import embedder
from app.rag.extractor import ExtractionError, extract_document, has_extractable_text
from app.rag.vector_store import vector_store
from app.services.audit_service import ACTION_DOC_FAILED, ACTION_DOC_PROCESSED, log_action

logger = logging.getLogger(__name__)


class TaskQueue(Protocol):
    """Seam for background execution (BackgroundTasks today, Celery later)."""

    def submit(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None: ...


class BackgroundTasksQueue:
    """Adapter around FastAPI's BackgroundTasks."""

    def __init__(self, background_tasks):
        self._background_tasks = background_tasks

    def submit(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        self._background_tasks.add_task(func, *args, **kwargs)


class InlineQueue:
    """Runs immediately. Used by tests so assertions see a finished document."""

    def submit(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        func(*args, **kwargs)


def documents_dir() -> Path:
    path = Path(settings.DOCUMENTS_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def process_document(document_id: int) -> None:
    """Extract -> clean -> chunk -> embed -> store. Owns its own DB session
    because it runs outside the request lifecycle.
    """
    from app.database.session import session_scope

    db = session_scope()
    started = time.perf_counter()
    try:
        document = db.get(Document, document_id)
        if document is None:
            logger.warning("process_document: document %s no longer exists", document_id)
            return

        logger.info("Processing document %s (%s)", document.id, document.original_filename)
        document.status = DocumentStatus.PROCESSING
        document.error_message = None
        db.commit()

        path = Path(document.file_path)
        if not path.exists():
            raise ExtractionError(f"Stored file is missing at {path}")

        pages = extract_document(path)
        if not has_extractable_text(pages):
            raise ExtractionError(
                "No extractable text found. This looks like a scanned or image-only "
                "document; it needs OCR before it can be indexed."
            )

        chunks = chunk_pages(
            pages,
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            id_prefix=f"doc{document.id}",
        )
        if not chunks:
            raise ExtractionError("Document produced no text chunks after cleaning.")

        vectors = embedder.embed_texts([c.text for c in chunks])

        # Embedding can take a while; the admin may have deleted the document
        # meanwhile. Check again so we never index chunks for a deleted record.
        db.expire_all()
        if db.get(Document, document_id) is None:
            logger.info("Document %s was deleted during processing; skipping indexing.", document_id)
            return

        # Replace any chunks from a previous run before inserting new ones.
        vector_store.delete_document(document.id)
        vector_store.add_chunks(
            chunks,
            vectors,
            metadata={
                "document_id": document.id,
                "filename": document.filename,
                "title": document.title,
                "department": document.department,
                "document_type": document.document_type.value,
                "academic_year": document.academic_year or "",
            },
        )

        document.page_count = len(pages)
        document.chunk_count = len(chunks)
        document.status = DocumentStatus.READY
        document.processed_at = datetime.now(timezone.utc)
        document.processing_seconds = round(time.perf_counter() - started, 2)
        document.error_message = None
        db.commit()

        log_action(
            db,
            ACTION_DOC_PROCESSED,
            target_type="document",
            target_id=document.id,
            detail=f"{len(pages)} pages, {len(chunks)} chunks in {document.processing_seconds}s",
        )
        logger.info(
            "Document %s ready: %d pages, %d chunks in %.2fs",
            document.id,
            len(pages),
            len(chunks),
            document.processing_seconds,
        )

    except Exception as exc:  # noqa: BLE001 - any failure marks the doc failed
        logger.exception("Processing failed for document %s", document_id)
        try:
            db.rollback()
            document = db.get(Document, document_id)
            if document is None:
                # Deleted while we were writing: remove anything we indexed.
                vector_store.delete_document(document_id)
            else:
                document.status = DocumentStatus.FAILED
                document.error_message = str(exc)[:1000]
                document.processing_seconds = round(time.perf_counter() - started, 2)
                db.commit()
                log_action(
                    db,
                    ACTION_DOC_FAILED,
                    target_type="document",
                    target_id=document_id,
                    detail=str(exc)[:500],
                )
        except Exception:  # noqa: BLE001
            logger.exception("Could not record failure for document %s", document_id)
    finally:
        db.close()


def delete_document_files(document: Document) -> None:
    """Remove the stored file from disk; a missing file is not an error."""
    try:
        path = Path(document.file_path)
        if path.exists():
            path.unlink()
    except OSError:
        logger.exception("Could not delete file for document %s", document.id)


def delete_document(db: Session, document: Document) -> dict[str, int]:
    """Remove a document from the vector store, disk, and the database."""
    removed_chunks = vector_store.delete_document(document.id)
    delete_document_files(document)
    db.delete(document)
    db.commit()
    return {"removed_chunks": removed_chunks}


def queue_processing(queue: TaskQueue, document_id: int) -> None:
    queue.submit(process_document, document_id)
