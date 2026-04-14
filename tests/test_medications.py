"""
Integration tests for /v1/medications/* endpoints.

QStashService is mocked by replacing the _qstash attribute on the
module-level medication_service singleton (created at router import time).
"""

import pytest
from unittest.mock import AsyncMock

from tests.conftest import FluentMock, make_table, TEST_USER_ID, TEST_MED_ID, TEST_SCHEDULE_ID


@pytest.fixture
def mock_qstash():
    """Replace QStash on the existing medication_service instance for the duration of the test."""
    from app.routers.medications import medication_service

    original = medication_service._qstash
    mock = AsyncMock()
    mock.sync_schedules.return_value = {"synced": 1}
    mock.delete_all_for_medication.return_value = None
    medication_service._qstash = mock
    yield mock
    medication_service._qstash = original


# ── GET /v1/medications ───────────────────────────────────────────────────

def test_get_medications_returns_list(client, mock_sb):
    mock_sb.table.return_value = FluentMock(select_data=[
        {
            "id": TEST_MED_ID,
            "name": "아스피린",
            "dosage": "100mg",
            "color_tag": "#1D9E75",
            "is_active": True,
            "schedules": [
                {"id": TEST_SCHEDULE_ID, "scheduled_time": "09:00:00", "cycle_type": "daily"},
            ],
        }
    ])

    resp = client.get("/v1/medications")

    assert resp.status_code == 200
    data = resp.json()
    assert "medications" in data
    assert len(data["medications"]) == 1
    assert data["medications"][0]["name"] == "아스피린"


def test_get_medications_empty(client, mock_sb):
    mock_sb.table.return_value = FluentMock(select_data=[])

    resp = client.get("/v1/medications")

    assert resp.status_code == 200
    assert resp.json()["medications"] == []


def test_get_medications_unauthorized(anon_client, mock_sb):
    mock_sb.auth.get_user.side_effect = Exception("Invalid token")

    resp = anon_client.get("/v1/medications", headers={"Authorization": "Bearer bad"})

    assert resp.status_code == 401


# ── POST /v1/medications ──────────────────────────────────────────────────

def test_create_medication_success(client, mock_sb, mock_qstash):
    meds_calls = iter([
        FluentMock(select_data=[]),                                                              # duplicate check → none found
        FluentMock(write_data=[{"id": TEST_MED_ID, "created_at": "2024-01-01T00:00:00"}]),     # insert
    ])
    mock_sb.table.side_effect = make_table({
        "users":       FluentMock(select_data=[{"id": TEST_USER_ID}]),
        "medications": FluentMock(select_data=[], write_data=[{"id": TEST_MED_ID, "created_at": "2024-01-01T00:00:00"}]),
        "schedules":   FluentMock(write_data=[{}]),
    })

    resp = client.post("/v1/medications", json={
        "name": "아스피린",
        "dosage": "100mg",
        "schedules": [
            {"scheduled_time": "09:00:00", "cycle_type": "daily"},
        ],
    })

    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == TEST_MED_ID
    assert data["name"] == "아스피린"
    mock_qstash.sync_schedules.assert_awaited_once()


def test_create_medication_duplicate_name(client, mock_sb, mock_qstash):
    mock_sb.table.side_effect = make_table({
        "users":       FluentMock(select_data=[{"id": TEST_USER_ID}]),
        "medications": FluentMock(select_data=[{"id": "existing-id"}]),   # duplicate found
    })

    resp = client.post("/v1/medications", json={
        "name": "아스피린",
        "schedules": [{"scheduled_time": "09:00:00", "cycle_type": "daily"}],
    })

    assert resp.status_code == 400
    assert resp.json()["detail"] == "DUPLICATE_MEDICATION_NAME"
    mock_qstash.sync_schedules.assert_not_awaited()


def test_create_medication_missing_name(client):
    resp = client.post("/v1/medications", json={
        "schedules": [{"scheduled_time": "09:00:00", "cycle_type": "daily"}],
    })
    assert resp.status_code == 422


def test_create_medication_missing_schedules(client):
    resp = client.post("/v1/medications", json={"name": "아스피린"})
    assert resp.status_code == 422


def test_create_medication_weekly_schedule(client, mock_sb, mock_qstash):
    mock_sb.table.side_effect = make_table({
        "users":       FluentMock(select_data=[{"id": TEST_USER_ID}]),
        "medications": FluentMock(select_data=[], write_data=[{"id": TEST_MED_ID, "created_at": "2024-01-01T00:00:00"}]),
        "schedules":   FluentMock(write_data=[{}]),
    })

    resp = client.post("/v1/medications", json={
        "name": "비타민",
        "schedules": [
            {
                "scheduled_time": "08:00:00",
                "cycle_type": "weekly",
                "cycle_value": {"weekdays": [1, 3, 5]},
            },
        ],
    })

    assert resp.status_code == 201


# ── PATCH /v1/medications/{id}/toggle ────────────────────────────────────

def test_toggle_medication_active_to_inactive(client, mock_sb, mock_qstash):
    """Toggle active → inactive: delete_all_for_medication must be called."""
    meds_calls = iter([
        FluentMock(select_data=[{"id": TEST_MED_ID}]),   # _verify_owner
        FluentMock(select_data={"is_active": True}),     # get current state
        FluentMock(write_data=[{}]),                     # update
    ])
    mock_sb.table.side_effect = lambda name: next(meds_calls)

    resp = client.patch(f"/v1/medications/{TEST_MED_ID}/toggle")

    assert resp.status_code == 200
    assert resp.json() == {"id": TEST_MED_ID, "is_active": False}
    mock_qstash.delete_all_for_medication.assert_awaited_once()
    mock_qstash.sync_schedules.assert_not_awaited()


def test_toggle_medication_inactive_to_active(client, mock_sb, mock_qstash):
    """Toggle inactive → active: sync_schedules must be called."""
    meds_calls = iter([
        FluentMock(select_data=[{"id": TEST_MED_ID}]),   # _verify_owner
        FluentMock(select_data={"is_active": False}),    # get current state
        FluentMock(write_data=[{}]),                     # update
    ])
    mock_sb.table.side_effect = lambda name: next(meds_calls)

    resp = client.patch(f"/v1/medications/{TEST_MED_ID}/toggle")

    assert resp.status_code == 200
    assert resp.json() == {"id": TEST_MED_ID, "is_active": True}
    mock_qstash.sync_schedules.assert_awaited_once()
    mock_qstash.delete_all_for_medication.assert_not_awaited()


def test_toggle_medication_not_owner(client, mock_sb, mock_qstash):
    mock_sb.table.return_value = FluentMock(select_data=[])   # _verify_owner → empty → 404

    resp = client.patch(f"/v1/medications/other-users-med/toggle")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "MEDICATION_NOT_FOUND"


# ── PATCH /v1/medications/{id} ────────────────────────────────────────────

def test_update_medication_name(client, mock_sb, mock_qstash):
    updated = {
        "id": TEST_MED_ID,
        "name": "이부프로펜",
        "dosage": "200mg",
        "color_tag": "#1D9E75",
        "is_active": True,
        "schedules": [
            {"id": TEST_SCHEDULE_ID, "scheduled_time": "09:00:00", "is_active": True},
        ],
    }

    meds_calls = iter([
        FluentMock(select_data=[{"id": TEST_MED_ID}]),   # _verify_owner
        FluentMock(write_data=[{}]),                     # update medications
        FluentMock(select_data=updated),                 # final fetch (single)
    ])
    schedules_calls = iter([
        FluentMock(write_data=[{}]),   # deactivate old schedules
        FluentMock(write_data=[{}]),   # insert new schedules
    ])

    def _table(name):
        if name == "medications":
            return next(meds_calls)
        if name == "schedules":
            return next(schedules_calls)
        return FluentMock()

    mock_sb.table.side_effect = _table

    resp = client.patch(f"/v1/medications/{TEST_MED_ID}", json={
        "name": "이부프로펜",
        "schedules": [{"scheduled_time": "09:00:00", "cycle_type": "daily"}],
    })

    assert resp.status_code == 200
    assert resp.json()["name"] == "이부프로펜"
    mock_qstash.sync_schedules.assert_awaited_once()


def test_update_medication_not_owner(client, mock_sb, mock_qstash):
    mock_sb.table.return_value = FluentMock(select_data=[])

    resp = client.patch(f"/v1/medications/other-users-med", json={"name": "이름 변경"})

    assert resp.status_code == 404


# ── DELETE /v1/medications/{id} ───────────────────────────────────────────

def test_delete_medication_success(client, mock_sb, mock_qstash):
    meds_calls = iter([
        FluentMock(select_data=[{"id": TEST_MED_ID}]),   # _verify_owner
        FluentMock(write_data=[{}]),                     # soft delete
    ])
    mock_sb.table.side_effect = lambda name: next(meds_calls)

    resp = client.delete(f"/v1/medications/{TEST_MED_ID}")

    assert resp.status_code == 200
    assert resp.json()["message"] == "Successfully deleted"
    mock_qstash.delete_all_for_medication.assert_awaited_once_with(TEST_MED_ID)


def test_delete_medication_not_found(client, mock_sb, mock_qstash):
    mock_sb.table.return_value = FluentMock(select_data=[])

    resp = client.delete("/v1/medications/nonexistent-id")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "MEDICATION_NOT_FOUND"
