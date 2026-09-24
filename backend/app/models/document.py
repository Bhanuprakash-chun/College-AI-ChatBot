"""Document model: an uploaded college document and its processing state."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.models.enums import DocumentStatus, DocumentType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Storage
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(100), default="application/pdf", nullable=False
    )
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Classification metadata, mirrored onto every chunk stored in ChromaDB
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str] = mapped_column(
        String(100), default="General", nullable=False, index=True
    )
    document_type: Mapped[DocumentType] = mapped_column(
        SAEnum(DocumentType, values_callable=lambda e: [m.value for m in e]),
        default=DocumentType.OTHER,
        nullable=False,
    )
    academic_year: Mapped[str] = mapped_column(String(20), default="", nullable=False)

    # Processing state
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(DocumentStatus, values_callable=lambda e: [m.value for m in e]),
        default=DocumentStatus.PROCESSING,
        nullable=False,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processing_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    uploaded_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
