"""Semantic retrieval: embed the question, search, apply the confidence gate.

Retrieval is purely embedding-based (cosine similarity over ChromaDB's HNSW
index). No keyword matching is used to find answers.
"""

import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.rag.embedder import Embedder, embedder as default_embedder
from app.rag.text_cleaner import clean_text
from app.rag.vector_store import VectorStore, vector_store as default_store

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    similarity: float
    document_id: int | None
    filename: str | None
    title: str | None
    page_number: int | None
    page_label: str | None
    department: str | None
    document_type: str | None
    academic_year: str | None

    @classmethod
    def from_hit(cls, hit: dict[str, Any]) -> "RetrievedChunk":
        return cls(
            chunk_id=hit.get("chunk_id", ""),
            text=hit.get("text", ""),
            similarity=float(hit.get("similarity", 0.0)),
            document_id=hit.get("document_id"),
            filename=hit.get("filename"),
            title=hit.get("title"),
            page_number=hit.get("page_number"),
            page_label=hit.get("page_label"),
            department=hit.get("department"),
            document_type=hit.get("document_type"),
            academic_year=hit.get("academic_year"),
        )


@dataclass
class RetrievalResult:
    query: str
    chunks: list[RetrievedChunk]       # only chunks clearing the threshold
    all_chunks: list[RetrievedChunk]   # unfiltered top-k, for diagnostics
    is_confident: bool
    top_similarity: float


class Retriever:
    def __init__(
        self,
        store: VectorStore | None = None,
        embedder_instance: Embedder | None = None,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
    ):
        self.store = store or default_store
        self.embedder = embedder_instance or default_embedder
        self.top_k = top_k or settings.TOP_K
        self.similarity_threshold = (
            settings.SIMILARITY_THRESHOLD if similarity_threshold is None else similarity_threshold
        )

    def retrieve(
        self,
        question: str,
        top_k: int | None = None,
        where: dict[str, Any] | None = None,
    ) -> RetrievalResult:
        k = top_k or self.top_k
        cleaned = clean_text(question) or question

        query_vector = self.embedder.embed_query(cleaned)
        hits = self.store.query(query_vector, top_k=k, where=where)
        chunks = [RetrievedChunk.from_hit(h) for h in hits]

        top_similarity = chunks[0].similarity if chunks else 0.0
        confident = [c for c in chunks if c.similarity >= self.similarity_threshold]
        is_confident = bool(confident)

        logger.debug(
            "Retrieval: q=%r hits=%d top_sim=%.3f threshold=%.2f confident=%s",
            cleaned[:80],
            len(chunks),
            top_similarity,
            self.similarity_threshold,
            is_confident,
        )

        return RetrievalResult(
            query=cleaned,
            chunks=confident,
            all_chunks=chunks,
            is_confident=is_confident,
            top_similarity=top_similarity,
        )


retriever = Retriever()
