"""ChromaDB persistence: chunk vectors plus the metadata answers cite.

Every chunk carries document_id, chunk_id, filename, page_number, department,
document_type and academic_year, so retrieval results can be filtered by
metadata and rendered as citations without a second database round trip.
"""

import logging
import threading
from typing import Any

from app.core.config import settings
from app.rag.chunker import Chunk

logger = logging.getLogger(__name__)


class VectorStore:
    """Thin wrapper over a persistent ChromaDB collection (cosine space)."""

    def __init__(self, persist_path: str | None = None, collection_name: str | None = None):
        self.persist_path = persist_path or settings.CHROMA_PATH
        self.collection_name = collection_name or settings.CHROMA_COLLECTION
        self._client = None
        self._collection = None
        self._lock = threading.RLock()  # reentrant: reset() calls _ensure()

    def _ensure(self):
        if self._collection is not None:
            return self._collection
        with self._lock:
            if self._collection is not None:
                return self._collection
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            self._client = chromadb.PersistentClient(
                path=self.persist_path,
                settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
            )
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            return self._collection

    @property
    def collection(self):
        return self._ensure()

    def count(self) -> int:
        try:
            return int(self.collection.count())
        except Exception:  # noqa: BLE001 - store unavailable should not 500 /health
            logger.exception("Could not count vector store")
            return 0

    def add_chunks(self, chunks: list[Chunk], embeddings, metadata: dict[str, Any]) -> None:
        """Insert one document's chunks. `metadata` is the per-document part."""
        if not chunks:
            return
        ids = [c.chunk_id for c in chunks]
        metadatas = []
        for chunk in chunks:
            entry = dict(metadata)
            entry.update(
                {
                    "chunk_id": chunk.chunk_id,
                    "chunk_index": chunk.index,
                    "page_number": chunk.pages[0] if chunk.pages else 0,
                    "page_label": chunk.page_label,
                    "char_count": chunk.char_count,
                }
            )
            metadatas.append(entry)

        self.collection.upsert(
            ids=ids,
            embeddings=[e.tolist() for e in embeddings],
            documents=[c.text for c in chunks],
            metadatas=metadatas,
        )

    def delete_document(self, document_id: int) -> int:
        """Remove every chunk belonging to one document. Returns rows removed."""
        try:
            existing = self.collection.get(where={"document_id": int(document_id)}, include=[])
            ids = existing.get("ids", []) or []
            if ids:
                self.collection.delete(ids=ids)
            return len(ids)
        except Exception:  # noqa: BLE001
            logger.exception("Failed deleting chunks for document %s", document_id)
            return 0

    def count_for_document(self, document_id: int) -> int:
        try:
            existing = self.collection.get(where={"document_id": int(document_id)}, include=[])
            return len(existing.get("ids", []) or [])
        except Exception:  # noqa: BLE001
            return 0

    def query(
        self,
        query_embedding,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search. Returns hits with `similarity` in [0, 1]."""
        if self.count() == 0:
            return []

        result = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=max(1, top_k),
            where=where or None,
            include=["documents", "metadatas", "distances"],
        )

        hits: list[dict[str, Any]] = []
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]

        for chunk_id, text, meta, distance in zip(ids, docs, metas, dists):
            meta = meta or {}
            # Chroma cosine distance is 1 - cosine_similarity for unit vectors.
            similarity = 1.0 - float(distance)
            hits.append(
                {
                    "chunk_id": chunk_id,
                    "text": text,
                    "similarity": max(0.0, min(1.0, similarity)),
                    "document_id": meta.get("document_id"),
                    "filename": meta.get("filename"),
                    "title": meta.get("title"),
                    "page_number": meta.get("page_number"),
                    "page_label": meta.get("page_label"),
                    "department": meta.get("department"),
                    "document_type": meta.get("document_type"),
                    "academic_year": meta.get("academic_year"),
                }
            )
        return hits

    def reset(self) -> None:
        """Drop and recreate the collection (used by tests and full re-index)."""
        with self._lock:
            self._ensure()
            try:
                self._client.delete_collection(self.collection_name)
            except Exception:  # noqa: BLE001 - collection may not exist yet
                pass
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )


vector_store = VectorStore()
