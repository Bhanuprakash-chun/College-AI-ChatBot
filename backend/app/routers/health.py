"""Health check: reports the real state of every dependency.

Anyone (load balancers, Docker healthchecks) gets the up/down summary. The
diagnostic detail -- database fallback reason, model list, error text, RAG
configuration -- is returned only to an authenticated admin, so the public
endpoint does not describe the system's internals.
"""

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.core.config import settings
from app.core.security import TokenError, decode_access_token
from app.database.session import db_state, init_engine, session_scope
from app.models.enums import UserRole
from app.models.user import User
from app.rag.ollama_client import ollama_client
from app.rag.vector_store import vector_store

router = APIRouter(tags=["System"])


def _is_admin_request(request: Request) -> bool:
    """True only for a valid bearer token belonging to an active admin."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return False
    try:
        payload = decode_access_token(header.split(" ", 1)[1].strip())
        user_id = int(payload["sub"])
    except (TokenError, KeyError, TypeError, ValueError):
        return False

    db = session_scope()
    try:
        user = db.get(User, user_id)
        return bool(user and user.is_active and user.role == UserRole.ADMIN)
    except Exception:  # noqa: BLE001 - health must never fail on this check
        return False
    finally:
        db.close()


@router.get("/health", summary="Service and dependency health")
def health(request: Request) -> dict:
    """Never throws. Each dependency is probed independently so a single
    outage shows up as one degraded component rather than a failed check.
    """
    database: dict = {"connected": False}
    database_error = None
    try:
        engine = init_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database["connected"] = True
    except Exception as exc:  # noqa: BLE001
        database_error = f"{type(exc).__name__}: {exc}"

    vector: dict = {"connected": False}
    vector_error = None
    try:
        vector = {"connected": True, "indexed_chunks": vector_store.count()}
    except Exception as exc:  # noqa: BLE001
        vector_error = f"{type(exc).__name__}: {exc}"

    llm_status = ollama_client.status()
    llm = {
        "available": llm_status.get("available", False),
        "model_pulled": llm_status.get("model_pulled", False),
    }

    components_ok = database["connected"] and vector["connected"]
    if components_ok and llm["available"] and llm["model_pulled"]:
        overall = "ok"
    elif components_ok:
        overall = "degraded"
    else:
        overall = "unhealthy"

    body = {
        "status": overall,
        "version": settings.APP_VERSION,
        "database": database,
        "vector_store": vector,
        "llm": llm,
    }

    if _is_admin_request(request):
        database["backend"] = db_state.backend
        database["fallback_reason"] = db_state.fallback_reason
        if database_error:
            database["error"] = database_error
        if vector_error:
            vector["error"] = vector_error
        llm.update(
            {
                "model": llm_status.get("model"),
                "models": llm_status.get("models", []),
                "detail": llm_status.get("detail"),
            }
        )
        body["environment"] = settings.ENVIRONMENT
        body["rag_config"] = {
            "embedding_model": settings.EMBEDDING_MODEL,
            "chunk_size": settings.CHUNK_SIZE,
            "chunk_overlap": settings.CHUNK_OVERLAP,
            "top_k": settings.TOP_K,
            "similarity_threshold": settings.SIMILARITY_THRESHOLD,
        }

    return body
