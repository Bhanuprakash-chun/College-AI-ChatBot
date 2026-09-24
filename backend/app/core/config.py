"""Central application configuration, loaded from environment / .env file.

Every tunable in the RAG pipeline (chunk size, top-k, similarity threshold,
model names) is exposed here so it can be changed without touching code.
"""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App ---
    APP_NAME: str = "College AI Assistant"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # --- Security ---
    # No default secret in production: startup refuses to run with the
    # placeholder value when ENVIRONMENT != development.
    SECRET_KEY: str = "CHANGE_ME_INSECURE_DEV_SECRET"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    BCRYPT_ROUNDS: int = 12

    # --- Database ---
    # Full SQLAlchemy URL. If unset, assembled from the MYSQL_* parts below;
    # if MySQL is unreachable at startup we fall back to SQLite automatically.
    DATABASE_URL: str = ""
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "college_ai"
    SQLITE_PATH: str = str(BASE_DIR / "college_ai.db")
    DB_ALLOW_SQLITE_FALLBACK: bool = True

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"

    # --- RAG: chunking ---
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 100

    # --- RAG: retrieval ---
    TOP_K: int = 5
    SIMILARITY_THRESHOLD: float = 0.30

    # --- RAG: models ---
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    OLLAMA_MODEL: str = "llama3.2:3b"
    # 127.0.0.1, not "localhost": on Windows, localhost tries IPv6 (::1) first
    # and stalls about 2 seconds per request when Ollama listens on IPv4 only.
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_TIMEOUT_SECONDS: int = 120
    OLLAMA_TEMPERATURE: float = 0.1
    # How long Ollama keeps the model in memory after a request. A cold load
    # of a 3B model can take over a minute, so keep it resident during use.
    OLLAMA_KEEP_ALIVE: str = "30m"
    # Load the embedding model and the LLM in the background at startup so
    # the first student question is not the one that pays the load cost.
    WARMUP_ON_STARTUP: bool = True

    # --- Vector store ---
    CHROMA_PATH: str = str(BASE_DIR.parent / "chroma_db")
    CHROMA_COLLECTION: str = "college_documents"

    # --- Uploads ---
    DOCUMENTS_DIR: str = str(BASE_DIR.parent / "documents")
    MAX_UPLOAD_MB: int = 25
    ALLOWED_UPLOAD_EXTENSIONS: str = ".pdf"

    # --- Conversation ---
    MAX_HISTORY_TURNS: int = 6

    # --- Rate limiting (requests per window, window in seconds) ---
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_LOGIN: str = "10/60"
    RATE_LIMIT_REGISTER: str = "5/300"
    RATE_LIMIT_CHAT: str = "30/60"
    RATE_LIMIT_UPLOAD: str = "20/300"

    # --- Bootstrap admin (created on first startup if no admin exists) ---
    BOOTSTRAP_ADMIN_EMAIL: str = "admin@college.edu"
    BOOTSTRAP_ADMIN_PASSWORD: str = ""
    BOOTSTRAP_ADMIN_NAME: str = "College Administrator"

    @field_validator("SIMILARITY_THRESHOLD")
    @classmethod
    def _check_threshold(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("SIMILARITY_THRESHOLD must be between 0 and 1")
        return v

    @field_validator("CHUNK_OVERLAP")
    @classmethod
    def _check_overlap(cls, v: int) -> int:
        if v < 0:
            raise ValueError("CHUNK_OVERLAP must be >= 0")
        return v

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_extensions(self) -> List[str]:
        return [e.strip().lower() for e in self.ALLOWED_UPLOAD_EXTENSIONS.split(",") if e.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024

    @property
    def mysql_url(self) -> str:
        pwd = self.MYSQL_PASSWORD
        from urllib.parse import quote_plus

        auth = self.MYSQL_USER if not pwd else f"{self.MYSQL_USER}:{quote_plus(pwd)}"
        return (
            f"mysql+pymysql://{auth}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/"
            f"{self.MYSQL_DATABASE}?charset=utf8mb4"
        )

    @property
    def sqlite_url(self) -> str:
        return f"sqlite:///{self.SQLITE_PATH}"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in {"production", "prod", "staging"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
