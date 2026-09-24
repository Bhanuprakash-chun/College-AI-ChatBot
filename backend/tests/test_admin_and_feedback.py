"""Feedback, admin user management, statistics, analytics, audit logs,
health, rate limiting and database-level behaviour."""

import io

import pytest

from app.core.rate_limit import SlidingWindowRateLimiter, parse_rule
from app.database.session import session_scope
from app.models.audit import AuditLog
from app.models.chat import ChatMessage, ChatSession
from app.models.enums import FeedbackRating, MessageRole, UserRole
from app.models.feedback import Feedback
from app.models.user import User


def _ask(client, headers, question="What is the minimum attendance percentage required?"):
    return client.post("/chat", json={"message": question}, headers=headers).json()


@pytest.fixture
def indexed(client, admin_headers, sample_pdf_bytes, inline_processing):
    response = client.post(
        "/admin/documents/upload",
        headers=admin_headers,
        files={"file": ("attendance_policy.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")},
        data={"title": "Attendance Policy", "department": "Academics"},
    )
    assert response.status_code == 201
    return response.json()["id"]


# --- feedback --------------------------------------------------------------


def test_feedback_is_recorded_on_an_assistant_answer(client, student_headers, indexed, stub_llm):
    stub_llm("echo")
    answer_id = _ask(client, student_headers)["assistant_message"]["id"]

    response = client.post(
        "/feedback", json={"message_id": answer_id, "rating": "up"}, headers=student_headers
    )
    assert response.status_code == 201
    assert response.json()["rating"] == "up"


def test_re_rating_updates_instead_of_duplicating(client, student_headers, indexed, stub_llm):
    stub_llm("echo")
    answer_id = _ask(client, student_headers)["assistant_message"]["id"]

    client.post("/feedback", json={"message_id": answer_id, "rating": "up"}, headers=student_headers)
    client.post(
        "/feedback",
        json={"message_id": answer_id, "rating": "down", "comment": "Missing the lab rule"},
        headers=student_headers,
    )

    db = session_scope()
    try:
        rows = db.query(Feedback).filter(Feedback.message_id == answer_id).all()
        assert len(rows) == 1
        assert rows[0].rating == FeedbackRating.DOWN
        assert rows[0].comment == "Missing the lab rule"
    finally:
        db.close()


def test_feedback_is_shown_when_the_session_is_reloaded(
    client, student_headers, indexed, stub_llm
):
    stub_llm("echo")
    body = _ask(client, student_headers)
    client.post(
        "/feedback",
        json={"message_id": body["assistant_message"]["id"], "rating": "up"},
        headers=student_headers,
    )
    detail = client.get(f"/chat/sessions/{body['session_id']}", headers=student_headers).json()
    assistant = [m for m in detail["messages"] if m["role"] == "assistant"][0]
    assert assistant["feedback"] == "up"


def test_feedback_on_a_user_message_is_rejected(client, student_headers, indexed, stub_llm):
    stub_llm("echo")
    user_message_id = _ask(client, student_headers)["user_message"]["id"]
    response = client.post(
        "/feedback", json={"message_id": user_message_id, "rating": "up"}, headers=student_headers
    )
    assert response.status_code == 400


def test_feedback_on_someone_elses_message_is_rejected(
    client, student_headers, indexed, stub_llm
):
    stub_llm("echo")
    answer_id = _ask(client, student_headers)["assistant_message"]["id"]

    other = client.post(
        "/auth/register",
        json={"email": "intruder@college.edu", "full_name": "Intruder", "password": "Passw0rd123"},
    ).json()
    response = client.post(
        "/feedback",
        json={"message_id": answer_id, "rating": "down"},
        headers={"Authorization": f"Bearer {other['access_token']}"},
    )
    assert response.status_code == 404


def test_feedback_on_a_missing_message_returns_404(client, student_headers):
    response = client.post(
        "/feedback", json={"message_id": 999999, "rating": "up"}, headers=student_headers
    )
    assert response.status_code == 404


def test_feedback_rejects_an_invalid_rating(client, student_headers):
    response = client.post(
        "/feedback", json={"message_id": 1, "rating": "meh"}, headers=student_headers
    )
    assert response.status_code == 422


def test_admin_sees_feedback_with_the_question_and_answer(
    client, student_headers, admin_headers, indexed, stub_llm
):
    stub_llm("echo")
    answer_id = _ask(client, student_headers)["assistant_message"]["id"]
    client.post(
        "/feedback",
        json={"message_id": answer_id, "rating": "down", "comment": "Too vague"},
        headers=student_headers,
    )

    listing = client.get("/admin/feedback?rating=down", headers=admin_headers).json()
    assert listing["total"] == 1
    item = listing["items"][0]
    assert item["comment"] == "Too vague"
    assert "attendance" in item["question"].lower()
    assert item["user_email"] == "student@test.edu"


# --- admin user management -------------------------------------------------


def test_admin_lists_users_with_activity_counts(
    client, student_headers, admin_headers, indexed, stub_llm
):
    stub_llm("echo")
    _ask(client, student_headers)
    listing = client.get("/admin/users?role=student", headers=admin_headers).json()
    assert listing["total"] == 1
    assert listing["items"][0]["message_count"] == 1
    assert listing["items"][0]["session_count"] == 1


def test_admin_can_promote_a_student(client, admin_headers, student_credentials):
    response = client.patch(
        f"/admin/users/{student_credentials['id']}",
        json={"role": "admin"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_admin_can_delete_a_student_and_their_history_cascades(
    client, student_headers, admin_headers, student_credentials, indexed, stub_llm
):
    stub_llm("echo")
    _ask(client, student_headers)

    response = client.delete(f"/admin/users/{student_credentials['id']}", headers=admin_headers)
    assert response.status_code == 200

    db = session_scope()
    try:
        assert db.get(User, student_credentials["id"]) is None
        assert (
            db.query(ChatSession).filter(ChatSession.user_id == student_credentials["id"]).count()
            == 0
        )
    finally:
        db.close()


def test_updating_a_missing_user_returns_404(client, admin_headers):
    assert (
        client.patch("/admin/users/999999", json={"is_active": False}, headers=admin_headers)
        .status_code
        == 404
    )


# --- statistics and analytics ---------------------------------------------


def test_statistics_reflect_real_activity(
    client, student_headers, admin_headers, indexed, stub_llm
):
    stub_llm("echo")
    _ask(client, student_headers)                                   # grounded
    _ask(client, student_headers, "What is the capital of France?")  # refused

    stats = client.get("/admin/statistics", headers=admin_headers).json()
    assert stats["total_documents"] == 1
    assert stats["documents_ready"] == 1
    assert stats["total_chunks"] > 0
    assert stats["total_questions"] == 2
    assert stats["grounded_answers"] == 1
    assert stats["fallback_answers"] == 1
    assert stats["grounded_rate"] == 0.5
    assert stats["active_users_7d"] == 1
    assert stats["total_students"] == 1


def test_analytics_report_questions_and_unanswered_topics(
    client, student_headers, admin_headers, indexed, stub_llm
):
    stub_llm("echo")
    _ask(client, student_headers)
    _ask(client, student_headers, "What is the capital of France?")

    analytics = client.get("/admin/analytics?days=7", headers=admin_headers).json()
    assert len(analytics["questions_per_day"]) == 7
    assert sum(d["count"] for d in analytics["questions_per_day"]) == 2
    assert "What is the capital of France?" in analytics["recent_unanswered"]
    assert analytics["top_documents"][0]["label"] == "Attendance Policy"
    # The one grounded answer is attributed to its top source's department.
    assert analytics["questions_by_department"] == [{"label": "Academics", "count": 1}]
    assert analytics["documents_by_department"] == [{"label": "Academics", "count": 1}]


# --- audit logs ------------------------------------------------------------


def test_security_events_are_audited(client, student_credentials, admin_headers):
    client.post(
        "/auth/login", json={"email": student_credentials["email"], "password": "Wrong@999"}
    )
    logs = client.get("/admin/audit-logs", headers=admin_headers).json()
    actions = {item["action"] for item in logs["items"]}
    assert "auth.login_failed" in actions
    assert "auth.login" in actions  # the admin's own login


def test_document_lifecycle_is_audited(client, admin_headers, indexed):
    client.delete(f"/admin/documents/{indexed}", headers=admin_headers)
    logs = client.get("/admin/audit-logs", headers=admin_headers).json()
    actions = [item["action"] for item in logs["items"]]
    for expected in ("document.upload", "document.processed", "document.delete"):
        assert expected in actions, f"missing {expected}"


def test_audit_logs_can_be_filtered_by_action(client, admin_headers, indexed):
    filtered = client.get("/admin/audit-logs?action=document.upload", headers=admin_headers).json()
    assert filtered["total"] == 1
    assert all(item["action"] == "document.upload" for item in filtered["items"])


# --- health ----------------------------------------------------------------


def test_public_health_reports_status_without_internals(client):
    body = client.get("/health").json()
    assert body["database"]["connected"] is True
    assert body["vector_store"]["connected"] is True
    assert "available" in body["llm"]
    assert body["status"] in ("ok", "degraded")
    # No configuration, model list, fallback reasons or error text for anonymous callers.
    assert "rag_config" not in body
    assert "fallback_reason" not in body["database"]
    assert "backend" not in body["database"]
    assert "models" not in body["llm"]


def test_health_shows_diagnostics_to_admins_only(client, admin_headers, student_headers):
    admin_view = client.get("/health", headers=admin_headers).json()
    assert admin_view["rag_config"]["top_k"] > 0
    assert "fallback_reason" in admin_view["database"]
    assert admin_view["database"]["backend"] in ("sqlite", "mysql")

    student_view = client.get("/health", headers=student_headers).json()
    assert "rag_config" not in student_view


def test_openapi_docs_are_served(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert "/chat" in client.get("/openapi.json").json()["paths"]


# --- rate limiting ---------------------------------------------------------


def test_rate_limiter_blocks_after_the_limit_and_reports_retry_after():
    limiter = SlidingWindowRateLimiter()
    for _ in range(3):
        allowed, _ = limiter.check("login:1.2.3.4", limit=3, window_seconds=60)
        assert allowed
    allowed, retry_after = limiter.check("login:1.2.3.4", limit=3, window_seconds=60)
    assert not allowed
    assert retry_after > 0


def test_rate_limiter_isolates_clients():
    limiter = SlidingWindowRateLimiter()
    for _ in range(3):
        limiter.check("login:1.1.1.1", limit=3, window_seconds=60)
    allowed, _ = limiter.check("login:2.2.2.2", limit=3, window_seconds=60)
    assert allowed


def test_parse_rule_rejects_malformed_rules():
    assert parse_rule("10/60") == (10, 60)
    with pytest.raises(ValueError):
        parse_rule("ten per minute")


def test_login_endpoint_returns_429_when_limited(client, student_credentials, monkeypatch):
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(rate_limit.login_rate_limit, "limit", 2)
    rate_limit.limiter.reset()

    payload = {"email": student_credentials["email"], "password": "Wrong@123"}
    codes = [client.post("/auth/login", json=payload).status_code for _ in range(3)]
    assert codes[:2] == [401, 401]
    assert codes[2] == 429


# --- database operations ---------------------------------------------------


def test_deleting_a_session_cascades_to_messages_and_feedback(
    client, student_headers, indexed, stub_llm
):
    stub_llm("echo")
    body = _ask(client, student_headers)
    client.post(
        "/feedback",
        json={"message_id": body["assistant_message"]["id"], "rating": "up"},
        headers=student_headers,
    )
    client.delete(f"/chat/sessions/{body['session_id']}", headers=student_headers)

    db = session_scope()
    try:
        assert db.query(ChatMessage).filter(ChatMessage.session_id == body["session_id"]).count() == 0
        assert db.query(Feedback).count() == 0
    finally:
        db.close()


def test_assistant_messages_persist_retrieval_provenance(
    client, student_headers, indexed, stub_llm
):
    stub_llm("echo")
    body = _ask(client, student_headers)
    db = session_scope()
    try:
        message = db.get(ChatMessage, body["assistant_message"]["id"])
        assert message.role == MessageRole.ASSISTANT
        assert message.grounded is True
        assert message.top_similarity > 0.3
        assert message.sources_json and "Attendance Policy" in message.sources_json
        assert message.latency_ms >= 0
    finally:
        db.close()


def test_email_uniqueness_is_enforced_case_insensitively(client):
    first = client.post(
        "/auth/register",
        json={"email": "Case@College.edu", "full_name": "Case One", "password": "Passw0rd123"},
    )
    second = client.post(
        "/auth/register",
        json={"email": "case@college.edu", "full_name": "Case Two", "password": "Passw0rd123"},
    )
    assert first.status_code == 201
    assert second.status_code == 409


def test_passwords_are_never_stored_in_plaintext(client):
    client.post(
        "/auth/register",
        json={"email": "plain@college.edu", "full_name": "Plain", "password": "Passw0rd123"},
    )
    db = session_scope()
    try:
        user = db.query(User).filter(User.email == "plain@college.edu").one()
        assert user.hashed_password != "Passw0rd123"
        assert user.role == UserRole.STUDENT
    finally:
        db.close()


def test_audit_log_rows_record_actor_and_ip(client, student_credentials):
    client.post(
        "/auth/login",
        json={"email": student_credentials["email"], "password": student_credentials["password"]},
    )
    db = session_scope()
    try:
        entry = (
            db.query(AuditLog)
            .filter(AuditLog.action == "auth.login")
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert entry.actor_email == student_credentials["email"]
        assert entry.ip_address
    finally:
        db.close()


# --- hardening regressions ----------------------------------------------------


def test_spoofed_forwarded_for_headers_do_not_bypass_rate_limits(
    client, student_credentials, monkeypatch
):
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(rate_limit.login_rate_limit, "limit", 2)
    rate_limit.limiter.reset()

    payload = {"email": student_credentials["email"], "password": "Wrong@123"}
    codes = [
        client.post(
            "/auth/login", json=payload, headers={"X-Forwarded-For": f"10.0.0.{i}"}
        ).status_code
        for i in range(3)
    ]
    assert codes[2] == 429, "a new X-Forwarded-For value must not reset the limit"


def test_unknown_email_login_still_runs_a_password_check(client, monkeypatch):
    """Keeps response time similar for known and unknown emails."""
    from app.routers import auth as auth_router

    calls = []
    monkeypatch.setattr(auth_router, "burn_password_check", lambda pw: calls.append(pw))
    response = client.post(
        "/auth/login", json={"email": "ghost@college.edu", "password": "Whatever@1"}
    )
    assert response.status_code == 401
    assert calls == ["Whatever@1"]


def test_oversized_upload_is_rejected_before_being_fully_read(
    client, admin_headers, monkeypatch
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    big = b"%PDF-1.4 " + b"0" * (1024 * 1024 + 10)
    response = client.post(
        "/admin/documents/upload",
        headers=admin_headers,
        files={"file": ("big.pdf", io.BytesIO(big), "application/pdf")},
        data={"title": "Too big"},
    )
    assert response.status_code == 400
    assert "limit" in response.json()["detail"]


def test_read_limited_stops_at_the_limit():
    import asyncio

    from app.utils.files import FileValidationError, read_limited

    class FakeUpload:
        def __init__(self, size):
            self.remaining = size
            self.reads = 0

        async def read(self, n):
            self.reads += 1
            take = min(n, self.remaining)
            self.remaining -= take
            return b"x" * take

    ok = FakeUpload(10)
    assert asyncio.run(read_limited(ok, max_bytes=100, chunk_size=4)) == b"x" * 10

    huge = FakeUpload(10_000)
    with pytest.raises(FileValidationError):
        asyncio.run(read_limited(huge, max_bytes=100, chunk_size=10))
    assert huge.reads <= 11, "reading must stop once the limit is passed"


def test_document_deleted_during_processing_leaves_no_chunks(
    client, admin_headers, sample_pdf_bytes, monkeypatch
):
    """Simulates an admin deleting a document while it is being embedded."""
    from app.database.session import session_scope
    from app.models.document import Document
    from app.rag.vector_store import vector_store
    from app.services import document_service

    # Upload without processing, so we control when processing runs.
    monkeypatch.setattr(
        "app.routers.admin.BackgroundTasksQueue",
        lambda background_tasks: type("Q", (), {"submit": lambda self, *a, **k: None})(),
    )
    doc_id = client.post(
        "/admin/documents/upload",
        headers=admin_headers,
        files={"file": ("attendance.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")},
        data={"title": "Attendance"},
    ).json()["id"]

    real_embed = document_service.embedder.embed_texts

    def embed_then_delete(texts, *args, **kwargs):
        vectors = real_embed(texts, *args, **kwargs)
        db = session_scope()
        try:
            db.delete(db.get(Document, doc_id))
            db.commit()
        finally:
            db.close()
        return vectors

    monkeypatch.setattr(document_service.embedder, "embed_texts", embed_then_delete)
    document_service.process_document(doc_id)

    assert vector_store.count_for_document(doc_id) == 0
