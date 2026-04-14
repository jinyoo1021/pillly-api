"""
Integration test configuration.

Strategy:
  - firebase_admin is mocked via sys.modules (module-level init would fail without credentials)
  - supabase.create_client is patched before app import (prevents real network connections)
  - get_current_user dependency is overridden per test via app.dependency_overrides
  - FluentMock mimics supabase's fluent query builder so services run their full logic
"""

import os
import sys
from unittest.mock import MagicMock, patch
import pytest

# ── 1. Test environment variables (must come before any app import) ────────
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("QSTASH_TOKEN", "local-dummy")
os.environ.setdefault("QSTASH_CURRENT_SIGNING_KEY", "local-dummy")
os.environ.setdefault("QSTASH_NEXT_SIGNING_KEY", "local-dummy")
os.environ.setdefault("FIREBASE_PROJECT_ID", "test-project")
os.environ.setdefault("FIREBASE_CREDENTIALS_PATH", "./secrets/firebase-adminsdk.json")
os.environ.setdefault("APNS_KEY_ID", "local-dummy")
os.environ.setdefault("APNS_TEAM_ID", "local-dummy")
os.environ.setdefault("APNS_PRIVATE_KEY_PATH", "./secrets/apns-key.p8")

# ── 2. Mock firebase_admin before any app import ───────────────────────────
# notification_service.py runs firebase_admin.initialize_app() at module level.
# Injecting a mock module prevents the credentials file from being read.
_mock_firebase = MagicMock()
_mock_firebase._apps = {"default": True}   # truthy → skips the if-not-_apps block
sys.modules["firebase_admin"] = _mock_firebase
sys.modules["firebase_admin.credentials"] = MagicMock()
sys.modules["firebase_admin.messaging"] = MagicMock()

# ── 3. Mock supabase.create_client before app import ──────────────────────
# app/core/supabase.py calls create_client() at module level.
_mock_supabase = MagicMock()
_sb_patcher = patch("supabase.create_client", return_value=_mock_supabase)
_sb_patcher.start()

# ── 4. Import app (all external deps are now safely mocked) ───────────────
from app.main import app                        # noqa: E402
from app.core.security import get_current_user  # noqa: E402
from fastapi.testclient import TestClient        # noqa: E402


# ── Shared test constants ──────────────────────────────────────────────────
TEST_USER_ID = "test-user-id-123"
TEST_MED_ID = "test-med-id-456"
TEST_SCHEDULE_ID = "test-schedule-id-789"


# ── FakeUser (returned by overridden get_current_user) ────────────────────
class FakeUser:
    id = TEST_USER_ID
    email = "test@example.com"
    user_metadata = {"name": "테스트 유저", "language": "ko"}
    app_metadata = {"provider": "email"}


FAKE_USER = FakeUser()


# ── FluentMock ────────────────────────────────────────────────────────────
class FluentMock:
    """
    Mimics supabase's fluent query builder.
    Every chain method returns self; execute() returns a result object whose
    .data is either select_data (reads) or write_data (inserts/updates/deletes).
    """

    def __init__(self, select_data=None, write_data=None):
        self._select_data = select_data if select_data is not None else []
        self._write_data = write_data if write_data is not None else (select_data or [])
        self._is_write = False

    # Read chain
    def select(self, *a, **kw): return self
    def eq(self, *a, **kw): return self
    def neq(self, *a, **kw): return self
    def is_(self, *a, **kw): return self
    def order(self, *a, **kw): return self
    def gte(self, *a, **kw): return self
    def lte(self, *a, **kw): return self
    def in_(self, *a, **kw): return self
    def single(self, *a, **kw): return self
    def limit(self, *a, **kw): return self

    # Write chain
    def update(self, *a, **kw):
        self._is_write = True
        return self

    def insert(self, *a, **kw):
        self._is_write = True
        return self

    def delete(self, *a, **kw):
        self._is_write = True
        return self

    def upsert(self, *a, **kw):
        self._is_write = True
        return self

    # Supabase filter property (e.g. .not_.is_(...))
    @property
    def not_(self):
        return self

    def execute(self):
        result = MagicMock()
        result.data = self._write_data if self._is_write else self._select_data
        return result


def make_table(data_map: dict):
    """
    Returns a side_effect function for mock_sb.table() that routes by table name.

    data_map values can be:
      - list           → FluentMock(select_data=list)
      - FluentMock     → used as-is (reset _is_write before returning)
    """
    def side_effect(table_name):
        entry = data_map.get(table_name)
        if entry is None:
            return FluentMock()
        if isinstance(entry, FluentMock):
            entry._is_write = False   # reset so the same instance can be reused
            return entry
        return FluentMock(select_data=entry)
    return side_effect


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_mock_supabase():
    """
    Reset the shared supabase mock before every test to prevent state leakage.
    side_effect=True and return_value=True ensure that side_effect set on child
    mocks (e.g. mock_sb.table.side_effect) is also cleared between tests.
    """
    _mock_supabase.reset_mock(side_effect=True, return_value=True)
    yield


@pytest.fixture
def mock_sb():
    """Exposes the shared mock supabase client for per-test configuration."""
    return _mock_supabase


@pytest.fixture
def client():
    """Authenticated TestClient — get_current_user is overridden to return FAKE_USER."""
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def anon_client():
    """Unauthenticated TestClient — uses the real get_current_user (Supabase token check)."""
    app.dependency_overrides.clear()
    with TestClient(app) as c:
        yield c
