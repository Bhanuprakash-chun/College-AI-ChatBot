"""Feedback route: thumbs up / thumbs down on an assistant answer."""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession, client_ip
from app.models.chat import ChatMessage, ChatSession
from app.models.enums import MessageRole
from app.models.feedback import Feedback
from app.schemas.chat import FeedbackOut, FeedbackRequest
from app.services.audit_service import ACTION_FEEDBACK, log_action

router = APIRouter(tags=["Feedback"])


@router.post(
    "/feedback",
    response_model=FeedbackOut,
    status_code=status.HTTP_201_CREATED,
    summary="Rate an assistant answer",
)
def submit_feedback(
    payload: FeedbackRequest, request: Request, user: CurrentUser, db: DbSession
) -> FeedbackOut:
    """Idempotent per (message, user): re-rating updates the existing row."""
    message = db.get(ChatMessage, payload.message_id)
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")

    # The message must be an assistant answer inside the caller's own session.
    session = db.get(ChatSession, message.session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")
    if message.role != MessageRole.ASSISTANT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feedback can only be given on assistant answers.",
        )

    existing = db.execute(
        select(Feedback).where(
            Feedback.message_id == message.id, Feedback.user_id == user.id
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.rating = payload.rating
        existing.comment = payload.comment
        db.commit()
        db.refresh(existing)
        record = existing
    else:
        record = Feedback(
            message_id=message.id,
            user_id=user.id,
            rating=payload.rating,
            comment=payload.comment,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    log_action(
        db,
        ACTION_FEEDBACK,
        actor=user,
        target_type="chat_message",
        target_id=message.id,
        detail=f"rating={payload.rating.value}",
        ip_address=client_ip(request),
    )
    return FeedbackOut.model_validate(record)
