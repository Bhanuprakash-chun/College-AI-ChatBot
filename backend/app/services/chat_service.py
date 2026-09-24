"""Chat orchestration: sessions, history, RAG invocation, persistence."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chat import ChatMessage, ChatSession
from app.models.enums import MessageRole
from app.models.feedback import Feedback
from app.models.user import User
from app.rag.pipeline import RAGResult, pipeline

logger = logging.getLogger(__name__)

TITLE_MAX = 60


def derive_title(question: str) -> str:
    """First question becomes the session title, trimmed at a word boundary."""
    cleaned = " ".join(question.split())
    if len(cleaned) <= TITLE_MAX:
        return cleaned or "New chat"
    return cleaned[:TITLE_MAX].rsplit(" ", 1)[0] + "..."


def get_or_create_session(db: Session, user: User, session_id: int | None) -> ChatSession:
    """Fetch a session owned by this user, or start a new one.

    Ownership is enforced here rather than in the router so that no chat path
    can read another student's conversation.
    """
    if session_id is not None:
        session = db.get(ChatSession, session_id)
        if session is None or session.user_id != user.id:
            raise PermissionError("Chat session not found for this user.")
        return session

    session = ChatSession(user_id=user.id, title="New chat")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def build_history(db: Session, session: ChatSession) -> list[dict]:
    """Recent turns for multi-turn context, oldest first, bounded in length."""
    limit = settings.MAX_HISTORY_TURNS * 2
    rows = (
        db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    rows = list(reversed(rows))
    return [{"role": m.role.value, "content": m.content} for m in rows]


def answer_question(
    db: Session,
    user: User,
    session: ChatSession,
    question: str,
) -> tuple[ChatMessage, ChatMessage, RAGResult]:
    """Run one turn: persist the question, run RAG, persist the answer."""
    history = build_history(db, session)

    user_message = ChatMessage(
        session_id=session.id,
        role=MessageRole.USER,
        content=question,
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    result = pipeline.answer(question, history=history)

    assistant_message = ChatMessage(
        session_id=session.id,
        role=MessageRole.ASSISTANT,
        content=result.answer,
        sources_json=json.dumps(result.citation_dicts()),
        grounded=result.grounded,
        top_similarity=result.top_similarity,
        llm_used=result.llm_used,
        latency_ms=result.latency_ms,
    )
    db.add(assistant_message)

    if session.title in ("New chat", "", None):
        session.title = derive_title(question)
    session.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(assistant_message)
    db.refresh(session)

    return user_message, assistant_message, result


def parse_citations(message: ChatMessage) -> list[dict]:
    if not message.sources_json:
        return []
    try:
        data = json.loads(message.sources_json)
        return data if isinstance(data, list) else []
    except (ValueError, TypeError):
        logger.warning("Malformed sources_json on message %s", message.id)
        return []


def feedback_map(db: Session, user: User, message_ids: list[int]) -> dict[int, str]:
    """message_id -> rating, for this user only."""
    if not message_ids:
        return {}
    rows = db.execute(
        select(Feedback.message_id, Feedback.rating).where(
            Feedback.user_id == user.id, Feedback.message_id.in_(message_ids)
        )
    ).all()
    return {mid: rating.value for mid, rating in rows}


def session_summaries(db: Session, user: User, search: str | None = None) -> list[dict]:
    """Sidebar/history list with message counts and a text preview."""
    query = select(ChatSession).where(ChatSession.user_id == user.id)
    if search:
        pattern = f"%{search.strip()}%"
        matching_session_ids = select(ChatMessage.session_id).where(
            ChatMessage.content.ilike(pattern)
        )
        query = query.where(
            ChatSession.title.ilike(pattern) | ChatSession.id.in_(matching_session_ids)
        )

    sessions = db.execute(query.order_by(ChatSession.updated_at.desc())).scalars().all()
    if not sessions:
        return []

    ids = [s.id for s in sessions]
    counts = dict(
        db.execute(
            select(ChatMessage.session_id, func.count(ChatMessage.id))
            .where(ChatMessage.session_id.in_(ids))
            .group_by(ChatMessage.session_id)
        ).all()
    )

    previews: dict[int, str] = {}
    for row in (
        db.execute(
            select(ChatMessage.session_id, ChatMessage.content)
            .where(ChatMessage.session_id.in_(ids), ChatMessage.role == MessageRole.USER)
            .order_by(ChatMessage.id.desc())
        )
        .all()
    ):
        previews.setdefault(row[0], (row[1] or "")[:120])

    return [
        {
            "id": s.id,
            "title": s.title,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
            "message_count": counts.get(s.id, 0),
            "preview": previews.get(s.id, ""),
        }
        for s in sessions
    ]
