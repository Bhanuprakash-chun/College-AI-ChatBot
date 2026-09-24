"""Document and admin-facing schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import DocumentStatus, DocumentType, FeedbackRating, UserRole


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    filename: str
    original_filename: str
    department: str
    document_type: DocumentType
    academic_year: str
    status: DocumentStatus
    page_count: int
    chunk_count: int
    file_size: int
    error_message: str | None = None
    processing_seconds: float | None = None
    created_at: datetime
    processed_at: datetime | None = None


class DocumentListOut(BaseModel):
    """Trimmed view for students: no file paths, no error internals."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    department: str
    document_type: DocumentType
    academic_year: str
    page_count: int
    created_at: datetime


class PaginatedDocuments(BaseModel):
    items: list[DocumentOut]
    total: int
    page: int
    page_size: int


class UserUpdateRequest(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
    department: str | None = Field(default=None, max_length=100)
    full_name: str | None = Field(default=None, min_length=2, max_length=150)


class PaginatedUsers(BaseModel):
    items: list["AdminUserOut"]
    total: int
    page: int
    page_size: int


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    department: str | None = None
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None
    session_count: int = 0
    message_count: int = 0


class StatisticsOut(BaseModel):
    total_users: int
    total_students: int
    total_admins: int
    active_users_7d: int
    total_documents: int
    documents_ready: int
    documents_processing: int
    documents_failed: int
    total_chunks: int
    total_questions: int
    total_sessions: int
    grounded_answers: int
    fallback_answers: int
    grounded_rate: float
    feedback_up: int
    feedback_down: int


class DailyCount(BaseModel):
    date: str
    count: int


class LabelCount(BaseModel):
    label: str
    count: int


class AnalyticsOut(BaseModel):
    questions_per_day: list[DailyCount]
    top_documents: list[LabelCount]
    questions_by_department: list[LabelCount]
    documents_by_department: list[LabelCount]
    grounded_vs_fallback: list[LabelCount]
    average_similarity: float
    average_latency_ms: float
    llm_answer_rate: float
    recent_unanswered: list[str]


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: int | None = None
    actor_email: str | None = None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    detail: str | None = None
    ip_address: str | None = None
    created_at: datetime


class PaginatedAuditLogs(BaseModel):
    items: list[AuditLogOut]
    total: int
    page: int
    page_size: int


class AdminFeedbackOut(BaseModel):
    id: int
    rating: FeedbackRating
    comment: str | None = None
    created_at: datetime
    user_email: str
    question: str
    answer: str
    grounded: bool
    top_similarity: float


class PaginatedFeedback(BaseModel):
    items: list[AdminFeedbackOut]
    total: int
    page: int
    page_size: int


PaginatedUsers.model_rebuild()
