"""Document upload, validation, processing, reprocess and delete."""

import io

from app.database.session import session_scope
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.rag.vector_store import vector_store
from app.utils.files import (
    FileValidationError,
    resolve_within,
    safe_filename,
    validate_extension,
    validate_pdf_magic,
    validate_size,
)


def _upload(client, headers, content: bytes, filename="attendance_policy.pdf", **form):
    data = {
        "title": form.get("title", "Attendance Policy"),
        "department": form.get("department", "Academics"),
        "document_type": form.get("document_type", "policy"),
        "academic_year": form.get("academic_year", "2025-26"),
    }
    return client.post(
        "/admin/documents/upload",
        headers=headers,
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
        data=data,
    )


# --- filename and validation helpers ---------------------------------------


def test_safe_filename_strips_path_traversal():
    generated = safe_filename("../../../../windows/system32/evil.pdf")
    assert "/" not in generated and "\\" not in generated
    assert ".." not in generated
    assert generated.endswith(".pdf")


def test_safe_filename_strips_dangerous_characters():
    generated = safe_filename('my"weird;file<name>.pdf')
    assert all(c.isalnum() or c in "._-" for c in generated)


def test_safe_filename_is_unique_per_call():
    assert safe_filename("policy.pdf") != safe_filename("policy.pdf")


def test_resolve_within_blocks_escaping_the_documents_directory(tmp_path):
    try:
        resolve_within(tmp_path, "../escaped.pdf")
    except FileValidationError:
        return
    raise AssertionError("path traversal was not blocked")


def test_validate_extension_rejects_disallowed_types():
    try:
        validate_extension("malware.exe", [".pdf"])
    except FileValidationError as exc:
        assert ".exe" in str(exc)
        return
    raise AssertionError("extension check did not reject .exe")


def test_validate_size_rejects_empty_and_oversized_files():
    for size in (0, 50 * 1024 * 1024):
        try:
            validate_size(size, 25 * 1024 * 1024)
        except FileValidationError:
            continue
        raise AssertionError(f"size {size} was not rejected")


def test_validate_pdf_magic_rejects_a_renamed_file():
    try:
        validate_pdf_magic(b"MZ\x90\x00 this is an executable")
    except FileValidationError as exc:
        assert "%PDF" in str(exc)
        return
    raise AssertionError("magic-byte check did not reject a non-PDF")


# --- upload ----------------------------------------------------------------


def test_upload_requires_admin(client, student_headers, sample_pdf_bytes):
    assert _upload(client, student_headers, sample_pdf_bytes).status_code == 403


def test_upload_requires_authentication(client, sample_pdf_bytes):
    assert _upload(client, {}, sample_pdf_bytes).status_code == 401


def test_upload_accepts_a_valid_pdf_and_returns_processing(
    client, admin_headers, sample_pdf_bytes
):
    response = _upload(client, admin_headers, sample_pdf_bytes)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] in ("processing", "ready")
    assert body["title"] == "Attendance Policy"
    assert body["department"] == "Academics"
    assert body["academic_year"] == "2025-26"


def test_upload_rejects_a_non_pdf_extension(client, admin_headers):
    response = client.post(
        "/admin/documents/upload",
        headers=admin_headers,
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        data={"title": "Notes"},
    )
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]


def test_upload_rejects_a_fake_pdf_with_a_real_extension(client, admin_headers):
    response = client.post(
        "/admin/documents/upload",
        headers=admin_headers,
        files={"file": ("evil.pdf", io.BytesIO(b"MZ\x90\x00 not a pdf"), "application/pdf")},
        data={"title": "Evil"},
    )
    assert response.status_code == 400
    assert "%PDF" in response.json()["detail"]


def test_upload_rejects_an_empty_file(client, admin_headers):
    response = client.post(
        "/admin/documents/upload",
        headers=admin_headers,
        files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
        data={"title": "Empty"},
    )
    assert response.status_code == 400


def test_uploading_the_same_file_twice_is_rejected(client, admin_headers, sample_pdf_bytes):
    assert _upload(client, admin_headers, sample_pdf_bytes).status_code == 201
    duplicate = _upload(client, admin_headers, sample_pdf_bytes)
    assert duplicate.status_code == 409


# --- processing ------------------------------------------------------------


def test_processing_indexes_the_document_and_marks_it_ready(
    client, admin_headers, sample_pdf_bytes, inline_processing
):
    response = _upload(client, admin_headers, sample_pdf_bytes)
    document_id = response.json()["id"]

    detail = client.get(f"/admin/documents/{document_id}", headers=admin_headers).json()
    assert detail["status"] == "ready", detail.get("error_message")
    assert detail["page_count"] >= 1
    assert detail["chunk_count"] >= 1
    assert vector_store.count_for_document(document_id) == detail["chunk_count"]


def test_processing_failure_marks_the_document_failed_with_a_reason(
    client, admin_headers, sample_pdf_bytes, inline_processing
):
    """Delete the stored file before processing runs, so extraction fails."""
    response = _upload(client, admin_headers, sample_pdf_bytes)
    document_id = response.json()["id"]

    # Corrupt the stored file, then reprocess.
    db = session_scope()
    try:
        document = db.get(Document, document_id)
        from pathlib import Path

        Path(document.file_path).unlink()
    finally:
        db.close()

    reprocess = client.post(
        f"/admin/documents/{document_id}/reprocess", headers=admin_headers
    )
    assert reprocess.status_code == 200

    detail = client.get(f"/admin/documents/{document_id}", headers=admin_headers).json()
    assert detail["status"] == "failed"
    assert detail["error_message"]


def test_reprocess_reindexes_without_duplicating_chunks(
    client, admin_headers, sample_pdf_bytes, inline_processing
):
    document_id = _upload(client, admin_headers, sample_pdf_bytes).json()["id"]
    first_count = vector_store.count_for_document(document_id)
    assert first_count > 0

    assert (
        client.post(f"/admin/documents/{document_id}/reprocess", headers=admin_headers).status_code
        == 200
    )
    assert vector_store.count_for_document(document_id) == first_count


def test_reprocess_of_a_missing_document_returns_404(client, admin_headers):
    assert (
        client.post("/admin/documents/999999/reprocess", headers=admin_headers).status_code == 404
    )


# --- listing ---------------------------------------------------------------


def test_admin_listing_paginates_and_filters(
    client, admin_headers, sample_pdf_bytes, second_pdf_bytes, inline_processing
):
    _upload(client, admin_headers, sample_pdf_bytes, filename="attendance_policy.pdf")
    _upload(
        client,
        admin_headers,
        second_pdf_bytes,
        filename="fees_structure.pdf",
        title="Fee Structure",
        department="Accounts",
    )

    listing = client.get("/admin/documents", headers=admin_headers).json()
    assert listing["total"] == 2

    filtered = client.get("/admin/documents?search=Fee", headers=admin_headers).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["title"] == "Fee Structure"

    ready = client.get("/admin/documents?status=ready", headers=admin_headers).json()
    assert ready["total"] == 2


def test_students_see_only_ready_documents_and_no_file_paths(
    client, admin_headers, student_headers, sample_pdf_bytes, inline_processing
):
    _upload(client, admin_headers, sample_pdf_bytes)

    response = client.get("/documents", headers=student_headers)
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert "file_path" not in items[0]
    assert "error_message" not in items[0]


def test_documents_listing_requires_authentication(client):
    assert client.get("/documents").status_code == 401


# --- delete ----------------------------------------------------------------


def test_delete_removes_the_document_its_file_and_its_chunks(
    client, admin_headers, sample_pdf_bytes, inline_processing
):
    from pathlib import Path

    document_id = _upload(client, admin_headers, sample_pdf_bytes).json()["id"]
    assert vector_store.count_for_document(document_id) > 0

    db = session_scope()
    try:
        stored_path = Path(db.get(Document, document_id).file_path)
    finally:
        db.close()
    assert stored_path.exists()

    response = client.delete(f"/admin/documents/{document_id}", headers=admin_headers)
    assert response.status_code == 200

    assert vector_store.count_for_document(document_id) == 0
    assert not stored_path.exists()
    assert (
        client.get(f"/admin/documents/{document_id}", headers=admin_headers).status_code == 404
    )


def test_delete_of_a_missing_document_returns_404(client, admin_headers):
    assert client.delete("/admin/documents/999999", headers=admin_headers).status_code == 404


def test_delete_requires_admin(client, student_headers, admin_headers, sample_pdf_bytes):
    document_id = _upload(client, admin_headers, sample_pdf_bytes).json()["id"]
    assert (
        client.delete(f"/admin/documents/{document_id}", headers=student_headers).status_code
        == 403
    )
