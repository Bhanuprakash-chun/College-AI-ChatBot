"""Audit logging. Never raises into the caller -- a failed audit write must
not break the operation it was recording, but it is logged loudly."""

import logging

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User

logger = logging.getLogger(__name__)

# Canonical action names, so the admin UI can filter on a known vocabulary.
ACTION_LOGIN = "auth.login"
ACTION_LOGIN_FAILED = "auth.login_failed"
ACTION_LOGOUT = "auth.logout"
ACTION_REGISTER = "auth.register"
ACTION_DOC_UPLOAD = "document.upload"
ACTION_DOC_PROCESSED = "document.processed"
ACTION_DOC_FAILED = "document.failed"
ACTION_DOC_DELETE = "document.delete"
ACTION_DOC_REPROCESS = "document.reprocess"
ACTION_USER_UPDATE = "user.update"
ACTION_USER_DELETE = "user.delete"
ACTION_CHAT_QUESTION = "chat.question"
ACTION_SESSION_DELETE = "chat.session_delete"
ACTION_FEEDBACK = "feedback.submit"


def log_action(
    db: Session,
    action: str,
    actor: User | None = None,
    target_type: str | None = None,
    target_id: str | int | None = None,
    detail: str | None = None,
    ip_address: str | None = None,
    commit: bool = True,
) -> AuditLog | None:
    try:
        entry = AuditLog(
            actor_id=actor.id if actor else None,
            actor_email=actor.email if actor else None,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            detail=detail[:2000] if detail else None,
            ip_address=ip_address,
        )
        db.add(entry)
        if commit:
            db.commit()
            db.refresh(entry)
        return entry
    except Exception:  # noqa: BLE001 - auditing must never break the request
        logger.exception("Failed to write audit log for action=%s", action)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
