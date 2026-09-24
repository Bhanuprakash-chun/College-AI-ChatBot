"""Chat routes: ask a question, manage sessions and history."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession, client_ip
from app.core.rate_limit import chat_rate_limit
from app.models.chat import ChatMessage, ChatSession
from app.schemas.auth import MessageResponse
from app.schemas.chat import (
    ChatMessageOut,
    ChatRequest,
    ChatResponse,
    SessionCreateRequest,
    SessionDetailOut,
    SessionOut,
)
from app.services import chat_service
from app.services.audit_service import ACTION_CHAT_QUESTION, ACTION_SESSION_DELETE, log_action

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Chat"])

SESSION_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found."
)


def _message_out(message: ChatMessage, rating: str | None = None) -> ChatMessageOut:
    return ChatMessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        grounded=message.grounded,
        top_similarity=message.top_similarity,
        llm_used=message.llm_used,
        latency_ms=message.latency_ms,
        created_at=message.created_at,
        citations=chat_service.parse_citations(message),
        feedback=rating,
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Depends(chat_rate_limit)],
    summary="Ask the assistant a question",
)
def chat(
    payload: ChatRequest, request: Request, user: CurrentUser, db: DbSession
) -> ChatResponse:
    try:
        session = chat_service.get_or_create_session(db, user, payload.session_id)
    except PermissionError as exc:
        raise SESSION_NOT_FOUND from exc

    try:
        user_message, assistant_message, result = chat_service.answer_question(
            db, user, session, payload.message
        )
    except Exception as exc:  # noqa: BLE001 - never leak internals to the client
        logger.exception("Chat failed for user %s", user.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The assistant is temporarily unavailable. Please try again shortly.",
        ) from exc

    log_action(
        db,
        ACTION_CHAT_QUESTION,
        actor=user,
        target_type="chat_session",
        target_id=session.id,
        detail=f"grounded={result.grounded} sim={result.top_similarity:.3f} llm={result.llm_used}",
        ip_address=client_ip(request),
    )

    return ChatResponse(
        session_id=session.id,
        session_title=session.title,
        user_message=_message_out(user_message),
        assistant_message=_message_out(assistant_message),
        grounded=result.grounded,
        llm_used=result.llm_used,
        degraded_reason=result.degraded_reason,
    )


@router.get("/chat/sessions", response_model=list[SessionOut], summary="List my chat sessions")
def list_sessions(
    user: CurrentUser,
    db: DbSession,
    search: str | None = Query(default=None, max_length=200, description="Filter by text"),
) -> list[SessionOut]:
    return [SessionOut(**row) for row in chat_service.session_summaries(db, user, search)]


@router.post(
    "/chat/sessions",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new chat session",
)
def create_session(payload: SessionCreateRequest, user: CurrentUser, db: DbSession) -> SessionOut:
    session = ChatSession(user_id=user.id, title=(payload.title or "New chat").strip() or "New chat")
    db.add(session)
    db.commit()
    db.refresh(session)
    return SessionOut(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=0,
        preview="",
    )


@router.get(
    "/chat/sessions/{session_id}",
    response_model=SessionDetailOut,
    summary="Get one session with its full message history",
)
def get_session(session_id: int, user: CurrentUser, db: DbSession) -> SessionDetailOut:
    session = db.get(ChatSession, session_id)
    if session is None or session.user_id != user.id:
        raise SESSION_NOT_FOUND

    messages = (
        db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.id.asc())
        )
        .scalars()
        .all()
    )
    ratings = chat_service.feedback_map(db, user, [m.id for m in messages])

    return SessionDetailOut(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=len(messages),
        preview=next((m.content[:120] for m in messages if m.role.value == "user"), ""),
        messages=[_message_out(m, ratings.get(m.id)) for m in messages],
    )


@router.delete(
    "/chat/sessions/{session_id}",
    response_model=MessageResponse,
    summary="Delete one of my chat sessions",
)
def delete_session(
    session_id: int, request: Request, user: CurrentUser, db: DbSession
) -> MessageResponse:
    session = db.get(ChatSession, session_id)
    if session is None or session.user_id != user.id:
        raise SESSION_NOT_FOUND

    db.delete(session)
    db.commit()

    log_action(
        db,
        ACTION_SESSION_DELETE,
        actor=user,
        target_type="chat_session",
        target_id=session_id,
        ip_address=client_ip(request),
    )
    return MessageResponse(message="Chat session deleted.")
