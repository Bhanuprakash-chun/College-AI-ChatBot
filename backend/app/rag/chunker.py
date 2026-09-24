"""Sentence-aware chunking with overlap.

CHUNK_SIZE / CHUNK_OVERLAP are measured in **characters**, not words. That is
deliberate: all-MiniLM-L6-v2 truncates its input at 256 word-pieces, so a
500-*word* chunk would have roughly half its text silently dropped before
embedding, quietly wrecking retrieval. At ~4 characters per token, a 500-char
chunk lands near 125 tokens and fits comfortably inside the model's window.

Chunks never straddle documents, and each one records the page numbers it was
drawn from so answers can cite "page 3".
"""

from dataclasses import dataclass, field

from app.rag.extractor import PageText
from app.rag.segmentation import sentence_tokenize
from app.rag.text_cleaner import clean_text

DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 100


@dataclass
class Chunk:
    chunk_id: str
    text: str
    pages: list[int] = field(default_factory=list)
    index: int = 0
    char_count: int = 0
    sentence_count: int = 0

    @property
    def page_label(self) -> str:
        if not self.pages:
            return ""
        if len(self.pages) == 1:
            return str(self.pages[0])
        return f"{self.pages[0]}-{self.pages[-1]}"


def _split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    """Hard-split a sentence that alone exceeds the chunk budget, on word
    boundaries, so no single piece overruns the embedding window.
    """
    words = sentence.split()
    pieces: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        added = len(word) + (1 if current else 0)
        if current and current_len + added > max_chars:
            pieces.append(" ".join(current))
            current, current_len = [word], len(word)
        else:
            current.append(word)
            current_len += added
    if current:
        pieces.append(" ".join(current))
    return pieces or [sentence[:max_chars]]


def _sentences_with_pages(pages: list[PageText], max_chars: int) -> list[tuple[str, int]]:
    """Flatten pages into (sentence, page_number) pairs after cleaning."""
    out: list[tuple[str, int]] = []
    for page in pages:
        cleaned = clean_text(page.text)
        if not cleaned:
            continue
        for sentence in sentence_tokenize(cleaned):
            if len(sentence) > max_chars:
                out.extend((piece, page.page_number) for piece in _split_long_sentence(sentence, max_chars))
            else:
                out.append((sentence, page.page_number))
    return out


def chunk_pages(
    pages: list[PageText],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    id_prefix: str = "doc",
) -> list[Chunk]:
    """Build overlapping, sentence-aligned chunks from one document's pages."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap >= chunk_size:
        # Guard against a config that would make the window never advance.
        chunk_overlap = max(0, chunk_size // 5)

    units = _sentences_with_pages(pages, max_chars=chunk_size)
    if not units:
        return []

    chunks: list[Chunk] = []
    start = 0
    chunk_index = 0

    while start < len(units):
        end = start
        length = 0
        sentences: list[str] = []
        page_numbers: set[int] = set()

        while end < len(units):
            sentence, page_number = units[end]
            addition = len(sentence) + (1 if sentences else 0)
            if sentences and length + addition > chunk_size:
                break
            sentences.append(sentence)
            page_numbers.add(page_number)
            length += addition
            end += 1

        text = " ".join(sentences).strip()
        if text:
            chunks.append(
                Chunk(
                    chunk_id=f"{id_prefix}::c{chunk_index}",
                    text=text,
                    pages=sorted(page_numbers),
                    index=chunk_index,
                    char_count=len(text),
                    sentence_count=len(sentences),
                )
            )
            chunk_index += 1

        if end >= len(units):
            break

        # Slide the window back far enough to carry ~chunk_overlap characters
        # of trailing context into the next chunk.
        overlap_chars = 0
        back = end
        while back > start + 1 and overlap_chars < chunk_overlap:
            back -= 1
            overlap_chars += len(units[back][0]) + 1

        start = back if back > start else start + 1

    return chunks
