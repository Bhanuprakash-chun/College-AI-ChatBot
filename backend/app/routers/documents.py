"""Student-facing document listing (metadata only, no file downloads)."""

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.schemas.document import DocumentListOut

router = APIRouter(tags=["Documents"])


@router.get(
    "/documents",
    response_model=list[DocumentListOut],
    summary="List the college documents the assistant can answer from",
)
def list_documents(
    user: CurrentUser,
    db: DbSession,
    department: str | None = Query(default=None, max_length=100),
    academic_year: str | None = Query(default=None, max_length=20),
) -> list[DocumentListOut]:
    """Students see only successfully indexed documents, and only their
    metadata -- never file paths, processing errors, or the raw file.
    """
    query = select(Document).where(Document.status == DocumentStatus.READY)
    if department:
        query = query.where(Document.department == department)
    if academic_year:
        query = query.where(Document.academic_year == academic_year)

    rows = db.execute(query.order_by(Document.created_at.desc())).scalars().all()
    return [DocumentListOut.model_validate(row) for row in rows]
