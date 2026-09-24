"""Text extraction with page numbers, behind a pluggable loader registry.

PDF is the only format wired up today. DOCX / TXT / HTML support is a matter
of registering another loader here -- nothing downstream (chunking, embedding,
retrieval) knows or cares about the source format.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


@dataclass
class PageText:
    """One page of extracted text, tagged so answers can cite a page number."""

    page_number: int  # 1-indexed
    text: str


class ExtractionError(Exception):
    """Raised when a document cannot be parsed at all."""


class Loader(Protocol):
    def __call__(self, path: Path) -> list[PageText]: ...


def extract_pdf(path: Path) -> list[PageText]:
    """Extract per-page text from a PDF using pypdf."""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(str(path))
    except (PdfReadError, OSError, ValueError) as exc:
        raise ExtractionError(f"Could not open PDF: {exc}") from exc

    if reader.is_encrypted:
        try:
            # Some PDFs are "encrypted" with an empty owner password.
            if reader.decrypt("") == 0:
                raise ExtractionError("PDF is password protected.")
        except Exception as exc:  # noqa: BLE001
            raise ExtractionError("PDF is password protected.") from exc

    pages: list[PageText] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - a single broken page must not kill the doc
            raw = ""
        pages.append(PageText(page_number=index, text=raw))

    if not pages:
        raise ExtractionError("PDF contains no pages.")
    return pages


def extract_txt(path: Path) -> list[PageText]:
    """Plain text: treated as a single page. Registered but not enabled by
    default -- add ".txt" to ALLOWED_UPLOAD_EXTENSIONS to turn it on.
    """
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ExtractionError(f"Could not read text file: {exc}") from exc
    return [PageText(page_number=1, text=content)]


LOADERS: dict[str, Callable[[Path], list[PageText]]] = {
    ".pdf": extract_pdf,
    ".txt": extract_txt,
}


def supported_extensions() -> list[str]:
    return sorted(LOADERS.keys())


def extract_document(path: Path) -> list[PageText]:
    """Dispatch to the loader registered for this file's extension."""
    loader = LOADERS.get(path.suffix.lower())
    if loader is None:
        raise ExtractionError(
            f"Unsupported file type '{path.suffix}'. Supported: {', '.join(supported_extensions())}"
        )
    return loader(path)


def has_extractable_text(pages: list[PageText], min_chars: int = 40) -> bool:
    """Detect scanned/image-only documents, which need OCR rather than parsing."""
    return sum(len(p.text.strip()) for p in pages) >= min_chars
