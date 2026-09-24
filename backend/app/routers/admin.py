"""Admin routes: document management, users, statistics, analytics,
feedback review and audit logs. Every route requires the admin role."""

import logging
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import func, select

from app.core.config import settings
from app.core.deps import AdminUser, DbSession, client_ip, require_admin
from app.core.rate_limit import upload_rate_limit
from app.models.audit import AuditLog
from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document
from app.models.enums import DocumentStatus, DocumentType, MessageRole, UserRole
from app.models.feedback import Feedback
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.document import (
    AdminFeedbackOut,
    AdminUserOut,
    AnalyticsOut,
    AuditLogOut,
    DocumentOut,
    PaginatedAuditLogs,
    PaginatedDocuments,
    PaginatedFeedback,
    PaginatedUsers,
    StatisticsOut,
    UserUpdateRequest,
)
from app.services import analytics_service
from app.services.audit_service import (
    ACTION_DOC_DELETE,
    ACTION_DOC_REPROCESS,
    ACTION_DOC_UPLOAD,
    ACTION_USER_DELETE,
    ACTION_USER_UPDATE,
    log_action,
)
from app.services.document_service import (
    BackgroundTasksQueue,
    delete_document,
    documents_dir,
    queue_processing,
)
from app.utils.files import (
    FileValidationError,
    read_limited,
    resolve_within,
    safe_filename,
    sha256_of,
    validate_extension,
    validate_pdf_magic,
    validate_size,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin)])

DOCUMENT_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Document not found."
)
USER_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")


# --------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------


@router.post(
    "/documents/upload",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(upload_rate_limit)],
    summary="Upload a college PDF for indexing",
)
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    admin: AdminUser,
    db: DbSession,
    file: UploadFile = File(..., description="The PDF to index"),
    title: str = Form(default="", max_length=255),
    department: str = Form(default="General", max_length=100),
    document_type: DocumentType = Form(default=DocumentType.OTHER),
    academic_year: str = Form(default="", max_length=20),
) -> DocumentOut:
    """Validates the upload, stores it under a safe name, then hands it to a
    background worker for extraction -> chunking -> embedding -> ChromaDB.
    Returns immediately with status `processing`.
    """
    try:
        extension = validate_extension(file.filename or "", settings.allowed_extensions)
        content = await read_limited(file, settings.max_upload_bytes)
        validate_size(len(content), settings.max_upload_bytes)
        if extension == ".pdf":
            validate_pdf_magic(content)
    except FileValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        await file.close()

    checksum = sha256_of(content)
    duplicate = db.execute(
        select(Document).where(Document.checksum == checksum)
    ).scalar_one_or_none()
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"This exact file is already uploaded as document #{duplicate.id} "
                f"('{duplicate.title}'). Delete it first to re-upload."
            ),
        )

    stored_name = safe_filename(file.filename or "document", extension)
    try:
        destination = resolve_within(documents_dir(), stored_name)
        destination.write_bytes(content)
    except (FileValidationError, OSError) as exc:
        logger.exception("Could not store upload")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the uploaded file.",
        ) from exc

    document = Document(
        filename=stored_name,
        original_filename=(file.filename or stored_name)[:255],
        file_path=str(destination),
        file_size=len(content),
        content_type=file.content_type or "application/pdf",
        checksum=checksum,
        title=(title.strip() or (file.filename or stored_name).rsplit(".", 1)[0])[:255],
        department=department.strip() or "General",
        document_type=document_type,
        academic_year=academic_year.strip(),
        status=DocumentStatus.PROCESSING,
        uploaded_by_id=admin.id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    log_action(
        db,
        ACTION_DOC_UPLOAD,
        actor=admin,
        target_type="document",
        target_id=document.id,
        detail=f"{document.original_filename} ({len(content)} bytes)",
        ip_address=client_ip(request),
    )

    queue_processing(BackgroundTasksQueue(background_tasks), document.id)
    return DocumentOut.model_validate(document)


@router.get("/documents", response_model=PaginatedDocuments, summary="List all documents")
def list_documents(
    admin: AdminUser,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: DocumentStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=200),
) -> PaginatedDocuments:
    query = select(Document)
    count_query = select(func.count(Document.id))

    if status_filter is not None:
        query = query.where(Document.status == status_filter)
        count_query = count_query.where(Document.status == status_filter)
    if search:
        pattern = f"%{search.strip()}%"
        condition = Document.title.ilike(pattern) | Document.original_filename.ilike(pattern)
        query = query.where(condition)
        count_query = count_query.where(condition)

    total = int(db.execute(count_query).scalar() or 0)
    rows = (
        db.execute(
            query.order_by(Document.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PaginatedDocuments(
        items=[DocumentOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/documents/{document_id}", response_model=DocumentOut, summary="Get one document")
def get_document(document_id: int, admin: AdminUser, db: DbSession) -> DocumentOut:
    document = db.get(Document, document_id)
    if document is None:
        raise DOCUMENT_NOT_FOUND
    return DocumentOut.model_validate(document)


@router.delete(
    "/documents/{document_id}", response_model=MessageResponse, summary="Delete a document"
)
def remove_document(
    document_id: int, request: Request, admin: AdminUser, db: DbSession
) -> MessageResponse:
    """Deletes the DB row, the stored file, and every chunk in ChromaDB."""
    document = db.get(Document, document_id)
    if document is None:
        raise DOCUMENT_NOT_FOUND

    title = document.title
    result = delete_document(db, document)

    log_action(
        db,
        ACTION_DOC_DELETE,
        actor=admin,
        target_type="document",
        target_id=document_id,
        detail=f"{title} ({result['removed_chunks']} chunks removed)",
        ip_address=client_ip(request),
    )
    return MessageResponse(
        message=f"Deleted '{title}' and removed {result['removed_chunks']} indexed chunks."
    )


@router.post(
    "/documents/{document_id}/reprocess",
    response_model=DocumentOut,
    summary="Re-run extraction and indexing for a document",
)
def reprocess_document(
    document_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    admin: AdminUser,
    db: DbSession,
) -> DocumentOut:
    document = db.get(Document, document_id)
    if document is None:
        raise DOCUMENT_NOT_FOUND

    document.status = DocumentStatus.PROCESSING
    document.error_message = None
    document.processed_at = None
    db.commit()
    db.refresh(document)

    log_action(
        db,
        ACTION_DOC_REPROCESS,
        actor=admin,
        target_type="document",
        target_id=document.id,
        detail=document.title,
        ip_address=client_ip(request),
    )

    queue_processing(BackgroundTasksQueue(background_tasks), document.id)
    return DocumentOut.model_validate(document)


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------


@router.get("/users", response_model=PaginatedUsers, summary="List users")
def list_users(
    admin: AdminUser,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    role: UserRole | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
) -> PaginatedUsers:
    query = select(User)
    count_query = select(func.count(User.id))

    if role is not None:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)
    if search:
        pattern = f"%{search.strip()}%"
        condition = User.email.ilike(pattern) | User.full_name.ilike(pattern)
        query = query.where(condition)
        count_query = count_query.where(condition)

    total = int(db.execute(count_query).scalar() or 0)
    rows = (
        db.execute(
            query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        .scalars()
        .all()
    )

    user_ids = [u.id for u in rows]
    session_counts: dict[int, int] = {}
    message_counts: dict[int, int] = {}
    if user_ids:
        session_counts = dict(
            db.execute(
                select(ChatSession.user_id, func.count(ChatSession.id))
                .where(ChatSession.user_id.in_(user_ids))
                .group_by(ChatSession.user_id)
            ).all()
        )
        message_counts = dict(
            db.execute(
                select(ChatSession.user_id, func.count(ChatMessage.id))
                .join(ChatMessage, ChatMessage.session_id == ChatSession.id)
                .where(
                    ChatSession.user_id.in_(user_ids),
                    ChatMessage.role == MessageRole.USER,
                )
                .group_by(ChatSession.user_id)
            ).all()
        )

    items = []
    for user in rows:
        data = AdminUserOut.model_validate(user)
        data.session_count = int(session_counts.get(user.id, 0))
        data.message_count = int(message_counts.get(user.id, 0))
        items.append(data)

    return PaginatedUsers(items=items, total=total, page=page, page_size=page_size)


@router.patch("/users/{user_id}", response_model=AdminUserOut, summary="Update a user")
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    request: Request,
    admin: AdminUser,
    db: DbSession,
) -> AdminUserOut:
    user = db.get(User, user_id)
    if user is None:
        raise USER_NOT_FOUND

    # An admin must not lock themselves out or drop the last admin account.
    if user.id == admin.id and (payload.role is not None and payload.role != UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove your own admin role.",
        )
    if user.id == admin.id and payload.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account.",
        )
    if (
        user.role == UserRole.ADMIN
        and payload.role is not None
        and payload.role != UserRole.ADMIN
    ):
        remaining = int(
            db.execute(
                select(func.count(User.id)).where(
                    User.role == UserRole.ADMIN, User.is_active.is_(True), User.id != user.id
                )
            ).scalar()
            or 0
        )
        if remaining == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one active admin account must remain.",
            )

    changes = []
    if payload.role is not None and payload.role != user.role:
        changes.append(f"role {user.role.value}->{payload.role.value}")
        user.role = payload.role
    if payload.is_active is not None and payload.is_active != user.is_active:
        changes.append(f"active {user.is_active}->{payload.is_active}")
        user.is_active = payload.is_active
    if payload.department is not None:
        user.department = payload.department
        changes.append("department updated")
    if payload.full_name is not None:
        user.full_name = payload.full_name
        changes.append("name updated")

    db.commit()
    db.refresh(user)

    log_action(
        db,
        ACTION_USER_UPDATE,
        actor=admin,
        target_type="user",
        target_id=user.id,
        detail="; ".join(changes) or "no changes",
        ip_address=client_ip(request),
    )
    return AdminUserOut.model_validate(user)


@router.delete("/users/{user_id}", response_model=MessageResponse, summary="Delete a user")
def delete_user(
    user_id: int, request: Request, admin: AdminUser, db: DbSession
) -> MessageResponse:
    user = db.get(User, user_id)
    if user is None:
        raise USER_NOT_FOUND
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account.",
        )
    if user.role == UserRole.ADMIN:
        remaining = int(
            db.execute(
                select(func.count(User.id)).where(User.role == UserRole.ADMIN, User.id != user.id)
            ).scalar()
            or 0
        )
        if remaining == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one admin account must remain.",
            )

    email = user.email
    db.delete(user)
    db.commit()

    log_action(
        db,
        ACTION_USER_DELETE,
        actor=admin,
        target_type="user",
        target_id=user_id,
        detail=email,
        ip_address=client_ip(request),
    )
    return MessageResponse(message=f"Deleted user {email} and all their chat history.")


# --------------------------------------------------------------------------
# Dashboard: statistics, analytics, feedback, audit
# --------------------------------------------------------------------------


@router.get("/statistics", response_model=StatisticsOut, summary="Dashboard counters")
def statistics(admin: AdminUser, db: DbSession) -> StatisticsOut:
    return StatisticsOut(**analytics_service.statistics(db))


@router.get("/analytics", response_model=AnalyticsOut, summary="Usage analytics")
def analytics(
    admin: AdminUser, db: DbSession, days: int = Query(default=14, ge=1, le=90)
) -> AnalyticsOut:
    return AnalyticsOut(**analytics_service.analytics(db, days=days))


@router.get("/feedback", response_model=PaginatedFeedback, summary="Review answer feedback")
def list_feedback(
    admin: AdminUser,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    rating: str | None = Query(default=None, pattern="^(up|down)$"),
) -> PaginatedFeedback:
    query = select(Feedback)
    count_query = select(func.count(Feedback.id))
    if rating:
        query = query.where(Feedback.rating == rating)
        count_query = count_query.where(Feedback.rating == rating)

    total = int(db.execute(count_query).scalar() or 0)
    rows = (
        db.execute(
            query.order_by(Feedback.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    items: list[AdminFeedbackOut] = []
    for entry in rows:
        message = db.get(ChatMessage, entry.message_id)
        user = db.get(User, entry.user_id)
        question = ""
        if message is not None:
            question = (
                db.execute(
                    select(ChatMessage.content)
                    .where(
                        ChatMessage.session_id == message.session_id,
                        ChatMessage.role == MessageRole.USER,
                        ChatMessage.id < message.id,
                    )
                    .order_by(ChatMessage.id.desc())
                    .limit(1)
                ).scalar()
                or ""
            )
        items.append(
            AdminFeedbackOut(
                id=entry.id,
                rating=entry.rating,
                comment=entry.comment,
                created_at=entry.created_at,
                user_email=user.email if user else "(deleted user)",
                question=question,
                answer=message.content if message else "(deleted message)",
                grounded=message.grounded if message else False,
                top_similarity=message.top_similarity if message else 0.0,
            )
        )

    return PaginatedFeedback(items=items, total=total, page=page, page_size=page_size)


@router.get("/audit-logs", response_model=PaginatedAuditLogs, summary="Security audit trail")
def list_audit_logs(
    admin: AdminUser,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    action: str | None = Query(default=None, max_length=80),
) -> PaginatedAuditLogs:
    query = select(AuditLog)
    count_query = select(func.count(AuditLog.id))
    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)

    total = int(db.execute(count_query).scalar() or 0)
    rows = (
        db.execute(
            query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return PaginatedAuditLogs(
        items=[AuditLogOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
