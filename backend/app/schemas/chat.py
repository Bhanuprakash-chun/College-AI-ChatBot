"""Chat, session and citation schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import FeedbackRating, MessageRole

MAX_QUESTION_CHARS = 2000


class CitationOut(BaseModel):
    document_id: int | None = None
    title: str
    filename: str
    page: str
    similarity: float
    snippet: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    session_id: int | None = Field(
        default=None, description="Existing session to append to; omit to start a new one."
    )

    @field_validator("message")
    @classmethod
    def _message(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Message cannot be empty.")
        return cleaned


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: MessageRole
    content: str
    grounded: bool = False
    top_similarity: float = 0.0
    llm_used: bool = False
    latency_ms: int = 0
    created_at: datetime
    citations: list[CitationOut] = Field(default_factory=list)
    feedback: FeedbackRating | None = None


class ChatResponse(BaseModel):
    session_id: int
    session_title: str
    user_message: ChatMessageOut
    assistant_message: ChatMessageOut
    grounded: bool
    llm_used: bool
    degraded_reason: str | None = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    preview: str = ""


class SessionDetailOut(SessionOut):
    messages: list[ChatMessageOut] = Field(default_factory=list)


class SessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class FeedbackRequest(BaseModel):
    message_id: int
    rating: FeedbackRating
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message_id: int
    rating: FeedbackRating
    comment: str | None = None
    created_at: datetime
