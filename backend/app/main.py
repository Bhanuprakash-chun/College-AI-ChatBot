"""FastAPI application entrypoint.

Boots the database (MySQL, or SQLite fallback), seeds a bootstrap admin when
one is configured, mounts every router, and installs handlers that keep
internal details out of HTTP error responses.
"""

import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.security import hash_password
from app.database.session import create_all, db_state, session_scope
from app.models.enums import UserRole
from app.models.user import User
from app.routers import admin, auth, chat, documents, feedback, health

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("app")
# Third-party clients log every HTTP call at INFO (each Ollama request, each
# Hugging Face cache check). Keep them for warnings and errors only.
for noisy in ("httpx", "httpcore", "huggingface_hub", "sentence_transformers", "chromadb"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


def _check_secret_key() -> None:
    """Refuse to serve production traffic with the placeholder secret."""
    if settings.SECRET_KEY == "CHANGE_ME_INSECURE_DEV_SECRET":
        if settings.is_production:
            raise RuntimeError(
                "SECRET_KEY is still the insecure default. Set a strong SECRET_KEY "
                "in the environment before running in production."
            )
        logger.warning(
            "SECRET_KEY is the insecure development default. Set SECRET_KEY in .env "
            "before deploying. Generate one with: python -c \"import secrets; "
            "print(secrets.token_urlsafe(48))\""
        )


def _bootstrap_admin() -> None:
    """Create the first admin account if none exists.

    The password must be supplied via BOOTSTRAP_ADMIN_PASSWORD. If it is not
    set, a random one is generated and printed once to the server log -- the
    app never ships with a known default credential.
    """
    db = session_scope()
    try:
        existing = int(
            db.execute(
                select(func.count(User.id)).where(User.role == UserRole.ADMIN)
            ).scalar()
            or 0
        )
        if existing:
            return

        password = settings.BOOTSTRAP_ADMIN_PASSWORD.strip()
        generated = False
        if not password:
            password = secrets.token_urlsafe(12)
            generated = True

        admin_user = User(
            email=settings.BOOTSTRAP_ADMIN_EMAIL.lower().strip(),
            full_name=settings.BOOTSTRAP_ADMIN_NAME,
            hashed_password=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin_user)
        db.commit()

        banner = "=" * 72
        if generated:
            logger.warning(
                "\n%s\nBOOTSTRAP ADMIN CREATED\n  email:    %s\n  password: %s\n"
                "  This password was generated randomly and is shown only once.\n"
                "  Set BOOTSTRAP_ADMIN_PASSWORD in .env to choose your own.\n%s",
                banner,
                admin_user.email,
                password,
                banner,
            )
        else:
            logger.info("Bootstrap admin created: %s", admin_user.email)
    except SQLAlchemyError:
        logger.exception("Could not create the bootstrap admin account")
        db.rollback()
    finally:
        db.close()


def _warm_up() -> None:
    """Runs in a daemon thread: never blocks startup, never crashes the app."""
    import time

    started = time.perf_counter()
    try:
        from app.rag.embedder import embedder

        embedder.embed_query("warm up")
        logger.info("Embedding model warm (%.1fs).", time.perf_counter() - started)
    except Exception:  # noqa: BLE001
        logger.exception("Embedding warm-up failed")

    try:
        from app.rag.ollama_client import ollama_client
        from app.rag.prompt import build_prompt

        llm_started = time.perf_counter()
        if ollama_client.warm_up(build_prompt("What are the college office timings?", [], [])):
            logger.info(
                "LLM '%s' loaded into memory (%.1fs).",
                settings.OLLAMA_MODEL,
                time.perf_counter() - llm_started,
            )
    except Exception:  # noqa: BLE001
        logger.exception("LLM warm-up failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _check_secret_key()

    Path(settings.DOCUMENTS_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.CHROMA_PATH).mkdir(parents=True, exist_ok=True)

    try:
        create_all()
        logger.info("Database ready (%s).", db_state.backend)
        if db_state.fallback_reason:
            logger.warning("Database fallback in effect: %s", db_state.fallback_reason)
    except Exception:
        logger.exception("Database initialisation failed")
        raise

    _bootstrap_admin()

    if settings.WARMUP_ON_STARTUP:
        import threading

        threading.Thread(target=_warm_up, name="model-warmup", daemon=True).start()

    logger.info(
        "RAG config: embedding=%s chunk=%s/%s top_k=%s threshold=%.2f llm=%s",
        settings.EMBEDDING_MODEL,
        settings.CHUNK_SIZE,
        settings.CHUNK_OVERLAP,
        settings.TOP_K,
        settings.SIMILARITY_THRESHOLD,
        settings.OLLAMA_MODEL,
    )
    yield
    from app.rag.ollama_client import ollama_client

    ollama_client.close()
    logger.info("Shutting down.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "A Retrieval-Augmented Generation assistant that answers student questions "
        "strictly from official college documents, with citations. Questions whose "
        "best retrieved passage scores below the similarity threshold are refused "
        "rather than answered from the model's own knowledge."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Readable field errors, without echoing the submitted values back."""
    errors = []
    for error in exc.errors():
        location = ".".join(str(p) for p in error.get("loc", []) if p != "body")
        errors.append({"field": location or "request", "message": error.get("msg", "Invalid value")})
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation failed.", "errors": errors},
    )


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("Database error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "A database error occurred. Please try again."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log the stack trace server-side; return an opaque message to the client."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred."},
    )


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(feedback.router)
app.include_router(documents.router)
app.include_router(admin.router)


@app.get("/api", tags=["System"], summary="API index")
def api_root() -> dict:
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
    }


# ------------------------------------------------------------------ #
# Serve the React SPA (built frontend)                                #
# ------------------------------------------------------------------ #

def _find_frontend_dir() -> Path | None:
    """Locate built React SPA across Docker and local development layouts."""
    import os

    configured = os.environ.get("FRONTEND_DIST")
    candidates = [
        Path(configured).resolve() if configured else None,
        Path(__file__).resolve().parents[1] / "static",            # Docker (/app/static) or backend/static
        Path(__file__).resolve().parents[2] / "frontend" / "dist",  # Local dev (repo_root/frontend/dist)
        Path(__file__).resolve().parents[2] / "static",            # repo_root/static
    ]
    for candidate in candidates:
        if candidate and candidate.is_dir() and (candidate / "index.html").is_file():
            return candidate
    return None


_FRONTEND_DIR = _find_frontend_dir()

if _FRONTEND_DIR:
    assets_dir = _FRONTEND_DIR / "assets"
    if assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(assets_dir)),
            name="frontend-assets",
        )

    @app.get("/", include_in_schema=False)
    async def serve_root():
        return FileResponse(str(_FRONTEND_DIR / "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # Unmatched API routes should return JSON 404, not HTML
        if full_path.startswith("api/") or full_path == "api":
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Not Found"})
        candidate = (_FRONTEND_DIR / full_path).resolve()
        if candidate.is_file() and _FRONTEND_DIR in candidate.parents:
            return FileResponse(str(candidate))
        return FileResponse(str(_FRONTEND_DIR / "index.html"))
else:
    @app.get("/", include_in_schema=False)
    async def serve_root_dev():
        return RedirectResponse(url="/docs")

