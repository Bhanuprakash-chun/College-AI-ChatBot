"""End-to-end RAG orchestration.

    question -> embedding -> semantic search -> top-K -> similarity threshold
             -> grounded context -> Ollama -> answer + citations

Grounding is enforced at three points:
  1. Below-threshold retrieval short-circuits to the fallback message; the LLM
     is never invoked, so it cannot invent an answer.
  2. The prompt forbids using anything outside the supplied context.
  3. Citations are built from the retrieved chunks' own metadata, not parsed
     out of the model's text, so a model that names a document cannot make the
     UI display a source that was not actually retrieved.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.rag.ollama_client import (
    OllamaClient,
    OllamaError,
    OllamaModelMissingError,
    OllamaUnavailableError,
    ollama_client as default_llm,
)
from app.rag.prompt import FALLBACK_MESSAGE, build_prompt
from app.rag.retriever import RetrievedChunk, Retriever, retriever as default_retriever

logger = logging.getLogger(__name__)

LLM_DOWN_NOTICE = (
    "The college assistant's language model is not running right now, so I can't "
    "write a summarised answer. Here is the relevant text from the official "
    "college documents instead:"
)


@dataclass
class Citation:
    document_id: int | None
    title: str
    filename: str
    page: str
    similarity: float
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "filename": self.filename,
            "page": self.page,
            "similarity": round(self.similarity, 4),
            "snippet": self.snippet,
        }


@dataclass
class RAGResult:
    question: str
    answer: str
    grounded: bool
    citations: list[Citation] = field(default_factory=list)
    top_similarity: float = 0.0
    llm_used: bool = False
    latency_ms: int = 0
    retrieved_count: int = 0
    degraded_reason: str | None = None

    def citation_dicts(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self.citations]


def _build_citations(chunks: list[RetrievedChunk], snippet_chars: int = 320) -> list[Citation]:
    """One citation per source document, keeping its best-scoring chunk."""
    best_by_doc: dict[Any, RetrievedChunk] = {}
    order: list[Any] = []
    for chunk in chunks:
        key = chunk.document_id if chunk.document_id is not None else chunk.filename
        if key not in best_by_doc:
            best_by_doc[key] = chunk
            order.append(key)
        elif chunk.similarity > best_by_doc[key].similarity:
            best_by_doc[key] = chunk

    citations: list[Citation] = []
    for key in order:
        chunk = best_by_doc[key]
        snippet = chunk.text.strip()
        if len(snippet) > snippet_chars:
            snippet = snippet[:snippet_chars].rsplit(" ", 1)[0] + "..."
        citations.append(
            Citation(
                document_id=chunk.document_id,
                title=chunk.title or chunk.filename or "College document",
                filename=chunk.filename or "",
                page=str(chunk.page_label or chunk.page_number or ""),
                similarity=chunk.similarity,
                snippet=snippet,
            )
        )
    return citations


# Words that point back at something said earlier ("does THAT include...").
_REFERRING_WORDS = re.compile(
    r"\b(it|its|that|this|those|these|they|them|their|there|same|above|ones|former|latter)\b",
    re.IGNORECASE,
)
# Openers that continue the previous question ("and the even semester?").
_CONTINUATION_OPENERS = re.compile(
    r"^\s*(and|also|what about|how about|then|so|but|or)\b", re.IGNORECASE
)


def is_follow_up(question: str) -> bool:
    """Does this question lean on the previous turn to make sense?

    This only decides whether to *rewrite the search query*. It never finds
    answers: retrieval itself stays purely embedding-based.
    """
    words = re.findall(r"[A-Za-z0-9']+", question)
    if len(words) <= 3:
        return True
    if _CONTINUATION_OPENERS.search(question):
        return True
    return bool(_REFERRING_WORDS.search(question))


def _contextualize(question: str, history: list[dict]) -> str:
    """Fold the previous student turn into the retrieval query for follow-ups.

    A follow-up like "does that include meals?" has no subject of its own and
    embeds as noise, so it is searched together with the previous question.
    A self-contained question is searched on its own: folding an unrelated
    earlier topic into it would inflate its similarity and let an off-topic
    question clear the threshold. The model always sees the original wording.
    """
    previous_user_turns = [t["content"] for t in history if t.get("role") == "user"]
    if not previous_user_turns or not is_follow_up(question):
        return question
    return f"{previous_user_turns[-1]} {question}"


_GLYPH_BULLET = re.compile(r"^(\s*)[•◦▪●·‣⁃]\s*", re.MULTILINE)


def normalize_markdown(text: str) -> str:
    """Small models often emit "•" bullets. Markdown does not treat those as
    list items, so a list would render as one run-on line. Rewrite them as
    "-" items, keeping indentation so nested lists stay nested.
    """
    return _GLYPH_BULLET.sub(lambda m: f"{m.group(1)}- ", text).strip()


def _is_refusal(answer_text: str) -> bool:
    """True when the model answered with the not-found sentence."""
    marker = FALLBACK_MESSAGE.split(".")[0].lower()
    return marker in answer_text.lower()


class RAGPipeline:
    def __init__(
        self,
        retriever_instance: Retriever | None = None,
        llm: OllamaClient | None = None,
    ):
        self.retriever = retriever_instance or default_retriever
        self.llm = llm or default_llm

    def answer(
        self,
        question: str,
        history: list[dict] | None = None,
        where: dict[str, Any] | None = None,
    ) -> RAGResult:
        started = time.perf_counter()
        history = history or []
        question = (question or "").strip()

        if not question:
            return RAGResult(
                question=question,
                answer="Please type a question about the college.",
                grounded=False,
                latency_ms=0,
            )

        search_query = _contextualize(question, history)
        retrieval = self.retriever.retrieve(search_query, where=where)

        # Guard 1: nothing cleared the similarity threshold -> refuse, no LLM call.
        if not retrieval.is_confident:
            elapsed = int((time.perf_counter() - started) * 1000)
            logger.info(
                "Fallback (below threshold %.2f, top=%.3f) for: %r",
                self.retriever.similarity_threshold,
                retrieval.top_similarity,
                question[:80],
            )
            return RAGResult(
                question=question,
                answer=FALLBACK_MESSAGE,
                grounded=False,
                citations=[],
                top_similarity=retrieval.top_similarity,
                llm_used=False,
                latency_ms=elapsed,
                retrieved_count=len(retrieval.all_chunks),
            )

        chunks = retrieval.chunks
        citations = _build_citations(chunks)
        prompt = build_prompt(question, chunks, history)

        llm_used = False
        degraded_reason: str | None = None
        try:
            generation = self.llm.generate(prompt)
            answer_text = normalize_markdown(generation.text)
            llm_used = True
            if not answer_text:
                answer_text = FALLBACK_MESSAGE
                citations = []
        except OllamaModelMissingError as exc:
            degraded_reason = str(exc)
            answer_text = self._degraded_answer(chunks)
        except (OllamaUnavailableError, OllamaError) as exc:
            degraded_reason = str(exc)
            answer_text = self._degraded_answer(chunks)
            logger.warning("Ollama unavailable, serving retrieved context: %s", exc)

        # The model judged the retrieved context insufficient. That is a refusal,
        # not a document-backed answer: no citations, and not counted as grounded.
        grounded = True
        if llm_used and _is_refusal(answer_text):
            answer_text = FALLBACK_MESSAGE
            citations = []
            grounded = False

        elapsed = int((time.perf_counter() - started) * 1000)
        return RAGResult(
            question=question,
            answer=answer_text,
            grounded=grounded,
            citations=citations,
            top_similarity=retrieval.top_similarity,
            llm_used=llm_used,
            latency_ms=elapsed,
            retrieved_count=len(retrieval.all_chunks),
            degraded_reason=degraded_reason,
        )

    @staticmethod
    def _degraded_answer(chunks: list[RetrievedChunk]) -> str:
        """LLM down: return the retrieved passages verbatim rather than nothing.

        This is still grounded -- it is the document text itself, with no
        generated content, so the no-hallucination contract holds.
        """
        parts = [LLM_DOWN_NOTICE, ""]
        for chunk in chunks[:3]:
            page = chunk.page_label or chunk.page_number or "?"
            parts.append(f"**{chunk.title or chunk.filename}** (page {page})")
            parts.append("")
            parts.append(f"> {chunk.text.strip()}")
            parts.append("")
        return "\n".join(parts).strip()

    def health(self) -> dict[str, Any]:
        return {
            "embedding_model": settings.EMBEDDING_MODEL,
            "llm": self.llm.status(),
            "top_k": self.retriever.top_k,
            "similarity_threshold": self.retriever.similarity_threshold,
            "indexed_chunks": self.retriever.store.count(),
        }


pipeline = RAGPipeline()
