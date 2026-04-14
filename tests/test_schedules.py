"""Integration tests for /v1/schedules/* endpoints."""

from datetime import date

from tests.conftest import FluentMock, make_table, TEST_MED_ID, TEST_SCHEDULE_ID


# ── GET /v1/schedules/today ───────────────────────────────────────────────

def test_get_today_schedule_with_daily_items(client, mock_sb):
    today = date.today().isoformat()

    mock_sb.table.side_effect = make_table({
        "medications": [
            {
                "id": TEST_MED_ID,
                "name": "아스피린",
                "color_tag": "#1D9E75",
                "schedules": [
                    {
                        "id": TEST_SCHEDULE_ID,
                        "scheduled_time": "09:00:00",
                        "cycle_type": "daily",
                        "cycle_value": None,
                        "is_active": True,
                    }
                ],
            }
        ],
        "dose_logs": [],   # no logs yet → all items are "pending"
    })

    resp = client.get("/v1/schedules/today")

    assert resp.status_code == 200
    data = resp.json()
    assert data["date"] == today
    assert data["total"] == 1
    assert data["done"] == 0
    assert data["rate"] == 0
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["schedule_id"] == TEST_SCHEDULE_ID
    assert item["medication_name"] == "아스피린"
    assert item["status"] == "pending"
    assert item["scheduled_time"] == "09:00"   # truncated to HH:MM


def test_get_today_schedule_with_done_dose(client, mock_sb):
    """Confirmed dose → item status should be 'done' and rate 100."""
    today = date.today().isoformat()

    mock_sb.table.side_effect = make_table({
        "medications": [
            {
                "id": TEST_MED_ID,
                "name": "아스피린",
                "color_tag": "#1D9E75",
                "schedules": [
                    {
                        "id": TEST_SCHEDULE_ID,
                        "scheduled_time": "09:00:00",
                        "cycle_type": "daily",
                        "cycle_value": None,
                        "is_active": True,
                    }
                ],
            }
        ],
        "dose_logs": [
            {"schedule_id": TEST_SCHEDULE_ID, "status": "done", "taken_at": "2024-01-15T09:05:00"},
        ],
    })

    resp = client.get("/v1/schedules/today")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["done"] == 1
    assert data["rate"] == 100
    assert data["items"][0]["status"] == "done"


def test_get_today_schedule_empty_no_medications(client, mock_sb):
    mock_sb.table.return_value = FluentMock(select_data=[])

    resp = client.get("/v1/schedules/today")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["done"] == 0
    assert data["rate"] == 0
    assert data["items"] == []


def test_get_today_schedule_inactive_schedule_excluded(client, mock_sb):
    """Inactive schedules must not appear in today's list."""
    mock_sb.table.side_effect = make_table({
        "medications": [
            {
                "id": TEST_MED_ID,
                "name": "아스피린",
                "color_tag": "#1D9E75",
                "schedules": [
                    {
                        "id": TEST_SCHEDULE_ID,
                        "scheduled_time": "09:00:00",
                        "cycle_type": "daily",
                        "cycle_value": None,
                        "is_active": False,   # inactive
                    }
                ],
            }
        ],
        "dose_logs": [],
    })

    resp = client.get("/v1/schedules/today")

    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["items"] == []


def test_get_today_schedule_unauthorized(anon_client, mock_sb):
    mock_sb.auth.get_user.side_effect = Exception("Invalid token")

    resp = anon_client.get("/v1/schedules/today", headers={"Authorization": "Bearer bad"})

    assert resp.status_code == 401
