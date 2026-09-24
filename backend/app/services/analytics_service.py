"""Dashboard statistics and analytics, computed from real table data."""

import json
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document
from app.models.enums import DocumentStatus, FeedbackRating, MessageRole, UserRole
from app.models.feedback import Feedback
from app.models.user import User
from app.rag.vector_store import vector_store


def _scalar(db: Session, stmt) -> int:
    return int(db.execute(stmt).scalar() or 0)


def statistics(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    total_users = _scalar(db, select(func.count(User.id)))
    total_students = _scalar(
        db, select(func.count(User.id)).where(User.role == UserRole.STUDENT)
    )
    total_admins = _scalar(db, select(func.count(User.id)).where(User.role == UserRole.ADMIN))

    active_user_ids = select(func.count(func.distinct(ChatSession.user_id))).where(
        ChatSession.updated_at >= week_ago
    )
    active_users_7d = _scalar(db, active_user_ids)

    total_documents = _scalar(db, select(func.count(Document.id)))
    ready = _scalar(
        db, select(func.count(Document.id)).where(Document.status == DocumentStatus.READY)
    )
    processing = _scalar(
        db, select(func.count(Document.id)).where(Document.status == DocumentStatus.PROCESSING)
    )
    failed = _scalar(
        db, select(func.count(Document.id)).where(Document.status == DocumentStatus.FAILED)
    )

    # Prefer the live vector-store count; fall back to the DB tally if the
    # store is unreachable, so the dashboard degrades instead of erroring.
    indexed_chunks = vector_store.count()
    if indexed_chunks == 0:
        indexed_chunks = _scalar(db, select(func.coalesce(func.sum(Document.chunk_count), 0)))

    total_questions = _scalar(
        db, select(func.count(ChatMessage.id)).where(ChatMessage.role == MessageRole.USER)
    )
    total_sessions = _scalar(db, select(func.count(ChatSession.id)))

    grounded = _scalar(
        db,
        select(func.count(ChatMessage.id)).where(
            ChatMessage.role == MessageRole.ASSISTANT, ChatMessage.grounded.is_(True)
        ),
    )
    fallback = _scalar(
        db,
        select(func.count(ChatMessage.id)).where(
            ChatMessage.role == MessageRole.ASSISTANT, ChatMessage.grounded.is_(False)
        ),
    )
    answered = grounded + fallback

    feedback_up = _scalar(
        db, select(func.count(Feedback.id)).where(Feedback.rating == FeedbackRating.UP)
    )
    feedback_down = _scalar(
        db, select(func.count(Feedback.id)).where(Feedback.rating == FeedbackRating.DOWN)
    )

    return {
        "total_users": total_users,
        "total_students": total_students,
        "total_admins": total_admins,
        "active_users_7d": active_users_7d,
        "total_documents": total_documents,
        "documents_ready": ready,
        "documents_processing": processing,
        "documents_failed": failed,
        "total_chunks": indexed_chunks,
        "total_questions": total_questions,
        "total_sessions": total_sessions,
        "grounded_answers": grounded,
        "fallback_answers": fallback,
        "grounded_rate": round(grounded / answered, 4) if answered else 0.0,
        "feedback_up": feedback_up,
        "feedback_down": feedback_down,
    }


def analytics(db: Session, days: int = 14) -> dict:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    rows = db.execute(
        select(ChatMessage.created_at).where(
            ChatMessage.role == MessageRole.USER, ChatMessage.created_at >= since
        )
    ).all()
    per_day = Counter(row[0].date().isoformat() for row in rows if row[0])
    questions_per_day = [
        {"date": (now - timedelta(days=offset)).date().isoformat(), "count": 0}
        for offset in range(days - 1, -1, -1)
    ]
    for entry in questions_per_day:
        entry["count"] = per_day.get(entry["date"], 0)

    assistant_rows = db.execute(
        select(
            ChatMessage.sources_json,
            ChatMessage.grounded,
            ChatMessage.top_similarity,
            ChatMessage.latency_ms,
            ChatMessage.llm_used,
        ).where(ChatMessage.role == MessageRole.ASSISTANT)
    ).all()

    doc_counter: Counter = Counter()
    top_source_doc_ids: list[int] = []
    similarities: list[float] = []
    latencies: list[int] = []
    grounded_count = 0
    llm_count = 0

    for sources_json, grounded, similarity, latency, llm_used in assistant_rows:
        if grounded:
            grounded_count += 1
            if similarity:
                similarities.append(float(similarity))
        if llm_used:
            llm_count += 1
        if latency:
            latencies.append(int(latency))
        if sources_json:
            try:
                citations = json.loads(sources_json)
                for citation in citations:
                    title = citation.get("title") or citation.get("filename")
                    if title:
                        doc_counter[title] += 1
                if grounded and citations and citations[0].get("document_id") is not None:
                    top_source_doc_ids.append(int(citations[0]["document_id"]))
            except (ValueError, TypeError, AttributeError):
                continue

    # Questions by department: attribute each grounded answer to the department
    # of its best-matching source document. Documents deleted since the answer
    # was given are reported as "Removed documents" rather than dropped.
    department_of: dict[int, str] = dict(
        db.execute(select(Document.id, Document.department)).all()
    )
    dept_counter: Counter = Counter(
        department_of.get(doc_id, "Removed documents") or "General"
        for doc_id in top_source_doc_ids
    )

    docs_by_dept_rows = db.execute(
        select(Document.department, func.count(Document.id))
        .where(Document.status == DocumentStatus.READY)
        .group_by(Document.department)
    ).all()

    unanswered_rows = db.execute(
        select(ChatMessage.session_id, ChatMessage.id)
        .where(ChatMessage.role == MessageRole.ASSISTANT, ChatMessage.grounded.is_(False))
        .order_by(ChatMessage.id.desc())
        .limit(10)
    ).all()

    recent_unanswered: list[str] = []
    for session_id, message_id in unanswered_rows:
        question = db.execute(
            select(ChatMessage.content)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == MessageRole.USER,
                ChatMessage.id < message_id,
            )
            .order_by(ChatMessage.id.desc())
            .limit(1)
        ).scalar()
        if question:
            recent_unanswered.append(question[:200])

    total_assistant = len(assistant_rows)

    return {
        "questions_per_day": questions_per_day,
        "top_documents": [
            {"label": label, "count": count} for label, count in doc_counter.most_common(8)
        ],
        "questions_by_department": [
            {"label": label, "count": count} for label, count in dept_counter.most_common(8)
        ],
        "documents_by_department": sorted(
            (
                {"label": dept or "General", "count": int(count)}
                for dept, count in docs_by_dept_rows
            ),
            key=lambda row: row["count"],
            reverse=True,
        ),
        "grounded_vs_fallback": [
            {"label": "Answered from documents", "count": grounded_count},
            {"label": "No relevant document", "count": total_assistant - grounded_count},
        ],
        "average_similarity": round(sum(similarities) / len(similarities), 4)
        if similarities
        else 0.0,
        "average_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
        "llm_answer_rate": round(llm_count / total_assistant, 4) if total_assistant else 0.0,
        "recent_unanswered": recent_unanswered,
    }
