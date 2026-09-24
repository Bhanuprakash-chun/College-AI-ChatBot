"""Upload safety: filename sanitisation, type/size validation, checksums.

Uploaded names are attacker-controlled. Every stored name is rebuilt from a
whitelist of characters plus a random suffix, and the final path is verified
to sit inside the documents directory before anything is written.
"""

import hashlib
import re
import secrets
import unicodedata
from pathlib import Path

MAX_STEM_LENGTH = 80
_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_PDF_MAGIC = b"%PDF-"


class FileValidationError(ValueError):
    """Raised when an upload fails type, size, or content validation."""


def safe_filename(original: str, extension: str | None = None) -> str:
    """Build a collision-free, path-traversal-proof storage filename."""
    name = unicodedata.normalize("NFKD", original or "document")
    name = name.encode("ascii", "ignore").decode("ascii")

    # Strip any directory component the client may have sent.
    name = name.replace("\\", "/").split("/")[-1]

    stem = Path(name).stem or "document"
    ext = (extension or Path(name).suffix or "").lower()

    stem = _SAFE_CHARS.sub("_", stem).strip("._-")
    stem = re.sub(r"_{2,}", "_", stem)
    if not stem:
        stem = "document"
    stem = stem[:MAX_STEM_LENGTH]

    ext = _SAFE_CHARS.sub("", ext)
    if ext and not ext.startswith("."):
        ext = f".{ext}"

    return f"{stem}_{secrets.token_hex(6)}{ext}"


def resolve_within(base_dir: Path, filename: str) -> Path:
    """Join and assert the result stays inside base_dir (traversal guard)."""
    base = base_dir.resolve()
    candidate = (base / filename).resolve()
    if base != candidate and base not in candidate.parents:
        raise FileValidationError("Resolved file path escapes the documents directory.")
    return candidate


def validate_extension(filename: str, allowed: list[str]) -> str:
    ext = Path(filename or "").suffix.lower()
    if not ext:
        raise FileValidationError("File has no extension.")
    if ext not in allowed:
        raise FileValidationError(
            f"File type '{ext}' is not allowed. Allowed types: {', '.join(allowed)}."
        )
    return ext


def validate_size(size_bytes: int, max_bytes: int) -> None:
    if size_bytes <= 0:
        raise FileValidationError("File is empty.")
    if size_bytes > max_bytes:
        raise FileValidationError(
            f"File is {size_bytes / 1_048_576:.1f} MB, which exceeds the "
            f"{max_bytes / 1_048_576:.0f} MB limit."
        )


async def read_limited(upload, max_bytes: int, chunk_size: int = 1024 * 1024) -> bytes:
    """Read an UploadFile without ever holding more than max_bytes + 1 chunk.

    Reading the whole body first and checking its length afterwards would let
    a single oversized upload exhaust server memory before being rejected.
    """
    buffer = bytearray()
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise FileValidationError(
                f"File exceeds the {max_bytes / 1_048_576:.0f} MB upload limit."
            )
    return bytes(buffer)


def validate_pdf_magic(content: bytes) -> None:
    """Check the real file signature, not just the declared extension."""
    if not content.startswith(_PDF_MAGIC):
        raise FileValidationError(
            "File does not look like a valid PDF (missing %PDF header). "
            "It may be renamed or corrupted."
        )


def sha256_of(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
