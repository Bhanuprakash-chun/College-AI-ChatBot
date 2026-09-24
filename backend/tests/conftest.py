"""Test fixtures.

Tests run against a real SQLite database and a real (temporary) ChromaDB
collection. Only the Ollama call is stubbed by default, because a 3B model
generating text would make the suite slow and non-deterministic -- the
retrieval, threshold, citation and persistence logic under test is all real.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Point every path-like setting at a throwaway directory BEFORE app import.
_TMP_ROOT = Path(tempfile.mkdtemp(prefix="collegeai_tests_"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_ROOT / 'test.db'}"
os.environ["CHROMA_PATH"] = str(_TMP_ROOT / "chroma")
os.environ["DOCUMENTS_DIR"] = str(_TMP_ROOT / "documents")
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production-use-only"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["BCRYPT_ROUNDS"] = "4"  # keep hashing fast in tests
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "BootstrapAdmin@123"
os.environ["ENVIRONMENT"] = "test"
os.environ["WARMUP_ON_STARTUP"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.database.session import Base, create_all, init_engine, session_scope  # noqa: E402
from app.main import app  # noqa: E402
from app.models.enums import UserRole  # noqa: E402
from app.models.user import User  # noqa: E402
from app.rag import pipeline as pipeline_module  # noqa: E402
from app.rag.ollama_client import Generation  # noqa: E402
from app.rag.vector_store import vector_store  # noqa: E402

SAMPLES_DIR = BACKEND_DIR.parent / "documents" / "samples"


@pytest.fixture(scope="session", autouse=True)
def _prepare_database():
    create_all()
    yield
    engine = init_engine()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_state():
    """Truncate tables and clear the vector store between tests."""
    engine = init_engine()
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.exec_driver_sql(f"DELETE FROM {table.name}")
    vector_store.reset()
    from app.core.rate_limit import limiter

    limiter.reset()
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


class StubLLM:
    """Deterministic stand-in for Ollama.

    `echo` mode returns a sentence quoting the first retrieved chunk, which is
    enough to assert the model was handed grounded context.
    """

    def __init__(self, mode: str = "echo", text: str = ""):
        self.mode = mode
        self.text = text
        self.calls: list[str] = []

    def generate(self, prompt: str, temperature=None):
        self.calls.append(prompt)
        if self.mode == "down":
            from app.rag.ollama_client import OllamaUnavailableError

            raise OllamaUnavailableError("Stubbed: Ollama is not running.")
        if self.mode == "missing_model":
            from app.rag.ollama_client import OllamaModelMissingError

            raise OllamaModelMissingError("Stubbed: model not pulled.")
        if self.mode == "empty":
            return Generation(text="", model="stub")
        if self.mode == "refuse":
            from app.rag.prompt import FALLBACK_MESSAGE

            return Generation(text=FALLBACK_MESSAGE, model="stub")
        if self.mode == "fixed":
            return Generation(text=self.text, model="stub")

        marker = "===== Context (official college documents) ====="
        context = prompt.split(marker, 1)[-1].split("=====", 1)[0].strip()
        first_line = next((ln for ln in context.splitlines() if ln and not ln.startswith("[")), "")
        return Generation(text=f"Based on the college documents: {first_line[:220]}", model="stub")

    def status(self):
        return {"available": self.mode != "down", "model": "stub", "model_pulled": True}


@pytest.fixture
def stub_llm(monkeypatch):
    """Install a stub LLM and hand the test a factory to change its mode."""

    def _install(mode: str = "echo", text: str = "") -> StubLLM:
        stub = StubLLM(mode=mode, text=text)
        monkeypatch.setattr(pipeline_module.pipeline, "llm", stub)
        return stub

    return _install


def _create_user(email: str, password: str, role: UserRole, name: str) -> int:
    db = session_scope()
    try:
        user = User(
            email=email,
            full_name=name,
            hashed_password=hash_password(password),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id
    finally:
        db.close()


@pytest.fixture
def student_credentials():
    email, password = "student@test.edu", "Student@123"
    user_id = _create_user(email, password, UserRole.STUDENT, "Test Student")
    return {"email": email, "password": password, "id": user_id}


@pytest.fixture
def admin_credentials():
    email, password = "admin@test.edu", "Admin@123"
    user_id = _create_user(email, password, UserRole.ADMIN, "Test Admin")
    return {"email": email, "password": password, "id": user_id}


def _auth_headers(client: TestClient, credentials: dict) -> dict:
    response = client.post(
        "/auth/login",
        json={"email": credentials["email"], "password": credentials["password"]},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def student_headers(client, student_credentials):
    return _auth_headers(client, student_credentials)


@pytest.fixture
def admin_headers(client, admin_credentials):
    return _auth_headers(client, admin_credentials)


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    pdf = SAMPLES_DIR / "attendance_policy.pdf"
    if not pdf.exists():
        pytest.skip(
            "Sample PDFs missing. Run: python scripts/generate_sample_documents.py"
        )
    return pdf.read_bytes()


@pytest.fixture
def second_pdf_bytes() -> bytes:
    pdf = SAMPLES_DIR / "fees_structure.pdf"
    if not pdf.exists():
        pytest.skip("Sample PDFs missing.")
    return pdf.read_bytes()


@pytest.fixture
def inline_processing(monkeypatch):
    """Make uploads index synchronously so assertions see a finished document."""
    from app.services import document_service

    class _Inline:
        def __init__(self, _background_tasks=None):
            pass

        def submit(self, func, *args, **kwargs):
            func(*args, **kwargs)

    monkeypatch.setattr(
        "app.routers.admin.BackgroundTasksQueue", lambda background_tasks: _Inline()
    )
    return document_service
