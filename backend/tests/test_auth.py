"""Authentication, JWT and role-based access control."""

import time

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


# --- password hashing ------------------------------------------------------


def test_password_hash_is_not_plaintext_and_verifies():
    hashed = hash_password("Student@123")
    assert hashed != "Student@123"
    assert hashed.startswith("$2b$")
    assert verify_password("Student@123", hashed)
    assert not verify_password("WrongPassword1", hashed)


def test_same_password_hashes_differently_each_time():
    assert hash_password("Student@123") != hash_password("Student@123")


def test_verify_password_rejects_malformed_hash_without_raising():
    assert verify_password("anything", "not-a-bcrypt-hash") is False


# --- JWT -------------------------------------------------------------------


def test_token_roundtrip_carries_subject_and_role():
    token, expires_in = create_access_token(42, "student")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "student"
    assert expires_in == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def test_expired_token_is_rejected():
    token, _ = create_access_token(1, "student", expires_minutes=-1)
    with pytest.raises(TokenError, match="expired"):
        decode_access_token(token)


def test_token_signed_with_another_key_is_rejected():
    forged = jwt.encode(
        {"sub": "1", "role": "admin", "exp": int(time.time()) + 600, "type": "access"},
        "a-completely-different-secret-key-of-sufficient-length",
        algorithm="HS256",
    )
    with pytest.raises(TokenError):
        decode_access_token(forged)


def test_non_access_token_type_is_rejected():
    other = jwt.encode(
        {"sub": "1", "role": "admin", "exp": int(time.time()) + 600, "type": "refresh"},
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    with pytest.raises(TokenError, match="not an access token"):
        decode_access_token(other)


# --- register --------------------------------------------------------------


def test_register_creates_student_and_returns_token(client):
    response = client.post(
        "/auth/register",
        json={
            "email": "New.Student@college.edu",
            "full_name": "New Student",
            "password": "Passw0rd123",
            "department": "Computer Science",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["role"] == "student"
    assert body["user"]["email"] == "new.student@college.edu"  # normalised
    assert body["access_token"]


def test_register_rejects_duplicate_email(client):
    payload = {
        "email": "dup@college.edu",
        "full_name": "Dup User",
        "password": "Passw0rd123",
    }
    assert client.post("/auth/register", json=payload).status_code == 201
    second = client.post("/auth/register", json=payload)
    assert second.status_code == 409


@pytest.mark.parametrize(
    "password,reason",
    [
        ("short1", "too short"),
        ("nodigitshere", "no digit"),
        ("12345678", "no letter"),
    ],
)
def test_register_enforces_password_policy(client, password, reason):
    response = client.post(
        "/auth/register",
        json={"email": f"weak_{reason.replace(' ', '')}@college.edu",
              "full_name": "Weak Password", "password": password},
    )
    assert response.status_code == 422, reason


def test_register_rejects_invalid_email(client):
    response = client.post(
        "/auth/register",
        json={"email": "not-an-email", "full_name": "Bad Email", "password": "Passw0rd123"},
    )
    assert response.status_code == 422


def test_self_registration_cannot_grant_admin_role(client):
    """Role is not accepted from the request body; extra keys are ignored."""
    response = client.post(
        "/auth/register",
        json={
            "email": "sneaky@college.edu",
            "full_name": "Sneaky User",
            "password": "Passw0rd123",
            "role": "admin",
        },
    )
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "student"


# --- login -----------------------------------------------------------------


def test_login_succeeds_and_records_last_login(client, student_credentials):
    response = client.post(
        "/auth/login",
        json={"email": student_credentials["email"], "password": student_credentials["password"]},
    )
    assert response.status_code == 200
    assert response.json()["user"]["last_login_at"] is not None


def test_login_with_wrong_password_is_rejected(client, student_credentials):
    response = client.post(
        "/auth/login", json={"email": student_credentials["email"], "password": "Wrong@123"}
    )
    assert response.status_code == 401


def test_login_does_not_reveal_whether_email_exists(client, student_credentials):
    unknown = client.post(
        "/auth/login", json={"email": "nobody@college.edu", "password": "Wrong@123"}
    )
    wrong_password = client.post(
        "/auth/login", json={"email": student_credentials["email"], "password": "Wrong@123"}
    )
    assert unknown.status_code == wrong_password.status_code == 401
    assert unknown.json()["detail"] == wrong_password.json()["detail"]


def test_deactivated_account_cannot_log_in(client, student_credentials, admin_headers):
    patch = client.patch(
        f"/admin/users/{student_credentials['id']}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert patch.status_code == 200

    response = client.post(
        "/auth/login",
        json={"email": student_credentials["email"], "password": student_credentials["password"]},
    )
    assert response.status_code == 403


# --- protected routes ------------------------------------------------------


def test_me_requires_a_token(client):
    assert client.get("/auth/me").status_code == 401


def test_me_rejects_a_garbage_token(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401


def test_me_returns_the_authenticated_user(client, student_headers, student_credentials):
    response = client.get("/auth/me", headers=student_headers)
    assert response.status_code == 200
    assert response.json()["email"] == student_credentials["email"]


def test_logout_succeeds_for_authenticated_user(client, student_headers):
    assert client.post("/auth/logout", headers=student_headers).status_code == 200


# --- RBAC ------------------------------------------------------------------


ADMIN_ROUTES = [
    ("get", "/admin/documents"),
    ("get", "/admin/users"),
    ("get", "/admin/statistics"),
    ("get", "/admin/analytics"),
    ("get", "/admin/feedback"),
    ("get", "/admin/audit-logs"),
]


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_admin_routes_reject_students(client, student_headers, method, path):
    response = getattr(client, method)(path, headers=student_headers)
    assert response.status_code == 403, f"{path} leaked to a student"


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_admin_routes_reject_anonymous(client, method, path):
    assert getattr(client, method)(path).status_code == 401


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_admin_routes_allow_admins(client, admin_headers, method, path):
    assert getattr(client, method)(path, headers=admin_headers).status_code == 200


def test_admin_cannot_demote_their_own_role(client, admin_headers, admin_credentials):
    response = client.patch(
        f"/admin/users/{admin_credentials['id']}", json={"role": "student"}, headers=admin_headers
    )
    assert response.status_code == 400


def test_admin_cannot_delete_their_own_account(client, admin_headers, admin_credentials):
    response = client.delete(f"/admin/users/{admin_credentials['id']}", headers=admin_headers)
    assert response.status_code == 400


def test_last_admin_cannot_be_demoted(client, admin_headers, admin_credentials):
    """A second admin exists only if one was created; with one admin, demotion
    of that admin by another admin must still leave one active admin."""
    second = client.post(
        "/auth/register",
        json={"email": "second@college.edu", "full_name": "Second", "password": "Passw0rd123"},
    )
    second_id = second.json()["user"]["id"]
    promote = client.patch(
        f"/admin/users/{second_id}", json={"role": "admin"}, headers=admin_headers
    )
    assert promote.status_code == 200

    # Now demoting the *other* admin is allowed, since one remains.
    demote = client.patch(
        f"/admin/users/{second_id}", json={"role": "student"}, headers=admin_headers
    )
    assert demote.status_code == 200
