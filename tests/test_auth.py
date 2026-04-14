"""
Integration tests for /v1/auth/* endpoints.

Auth endpoints call supabase.auth.* directly (not supabase.table),
so we configure mock_sb.auth.* return values per test.
"""

from unittest.mock import MagicMock


# ── Fake Supabase auth response objects ───────────────────────────────────

class _Session:
    access_token = "test-access-token"
    refresh_token = "test-refresh-token"


class _User:
    id = "supabase-user-id"
    email = "user@example.com"
    user_metadata = {"name": "홍길동", "language": "ko"}
    app_metadata = {"provider": "email"}


class _AuthResponse:
    user = _User()
    session = _Session()


class _RefreshResponse:
    session = _Session()


# ── POST /v1/auth/register ────────────────────────────────────────────────

def test_register_success(anon_client, mock_sb):
    mock_sb.auth.sign_up.return_value = _AuthResponse()

    resp = anon_client.post("/v1/auth/register", json={
        "email": "user@example.com",
        "password": "securepass123",
        "name": "홍길동",
    })

    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "user@example.com"
    assert data["user_id"] == "supabase-user-id"
    assert "access_token" in data
    assert "refresh_token" in data


def test_register_duplicate_email(anon_client, mock_sb):
    """Supabase returns user=None when email is already registered."""
    no_user = MagicMock()
    no_user.user = None
    mock_sb.auth.sign_up.return_value = no_user

    resp = anon_client.post("/v1/auth/register", json={
        "email": "existing@example.com",
        "password": "securepass123",
        "name": "홍길동",
    })

    assert resp.status_code == 400
    assert resp.json()["detail"] == "EMAIL_ALREADY_EXISTS"


def test_register_invalid_email(anon_client):
    resp = anon_client.post("/v1/auth/register", json={
        "email": "not-an-email",
        "password": "securepass123",
        "name": "홍길동",
    })
    assert resp.status_code == 422


def test_register_missing_required_fields(anon_client):
    resp = anon_client.post("/v1/auth/register", json={})
    assert resp.status_code == 422


def test_register_missing_name(anon_client):
    resp = anon_client.post("/v1/auth/register", json={
        "email": "user@example.com",
        "password": "securepass123",
    })
    assert resp.status_code == 422


# ── POST /v1/auth/login ───────────────────────────────────────────────────

def test_login_success(anon_client, mock_sb):
    mock_sb.auth.sign_in_with_password.return_value = _AuthResponse()

    resp = anon_client.post("/v1/auth/login", json={
        "email": "user@example.com",
        "password": "securepass123",
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"] == "test-access-token"
    assert data["refresh_token"] == "test-refresh-token"
    assert data["user"]["email"] == "user@example.com"
    assert data["user"]["name"] == "홍길동"


def test_login_wrong_password(anon_client, mock_sb):
    mock_sb.auth.sign_in_with_password.side_effect = Exception("Invalid login credentials")

    resp = anon_client.post("/v1/auth/login", json={
        "email": "user@example.com",
        "password": "wrongpassword",
    })

    assert resp.status_code == 401
    assert resp.json()["detail"] == "INVALID_CREDENTIALS"


def test_login_missing_required_fields(anon_client):
    resp = anon_client.post("/v1/auth/login", json={})
    assert resp.status_code == 422


# ── POST /v1/auth/refresh ─────────────────────────────────────────────────

def test_refresh_token_success(anon_client, mock_sb):
    mock_sb.auth.refresh_access_token.return_value = _RefreshResponse()

    resp = anon_client.post("/v1/auth/refresh", json={
        "refresh_token": "old-refresh-token",
    })

    assert resp.status_code == 200
    assert resp.json()["access_token"] == "test-access-token"


def test_refresh_token_invalid(anon_client, mock_sb):
    mock_sb.auth.refresh_access_token.side_effect = Exception("Token expired")

    resp = anon_client.post("/v1/auth/refresh", json={
        "refresh_token": "bad-token",
    })

    assert resp.status_code == 401


# ── DELETE /v1/auth/logout ────────────────────────────────────────────────

def test_logout_success(anon_client, mock_sb):
    mock_sb.auth.sign_out.return_value = None

    resp = anon_client.delete("/v1/auth/logout", headers={
        "Authorization": "Bearer some-token",
    })

    assert resp.status_code == 200
    assert resp.json()["message"] == "Successfully logged out"


# ── Auth guard ────────────────────────────────────────────────────────────

def test_protected_endpoint_with_invalid_token(anon_client, mock_sb):
    """Invalid JWT → Supabase rejects → 401."""
    mock_sb.auth.get_user.side_effect = Exception("JWT expired")

    resp = anon_client.get("/v1/medications", headers={
        "Authorization": "Bearer expired-token",
    })

    assert resp.status_code == 401


def test_protected_endpoint_without_authorization_header(anon_client):
    """Missing Authorization header → FastAPI returns 422 (required header missing)."""
    resp = anon_client.get("/v1/medications")
    assert resp.status_code == 422
