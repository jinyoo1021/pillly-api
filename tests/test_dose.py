"""
Integration tests for /v1/dose/* endpoints.

All tests use the authenticated `client` fixture.
Supabase queries are intercepted via FluentMock on mock_sb.table.
"""

from tests.conftest import FluentMock, make_table, TEST_USER_ID, TEST_MED_ID, TEST_SCHEDULE_ID

TAKEN_AT = "2024-01-15T09:05:00+00:00"
LOG_DATE = "2024-01-15"


# ── POST /v1/dose/confirm ─────────────────────────────────────────────────

def test_confirm_dose_new_log(client, mock_sb):
    """No existing log → insert new 'done' record."""
    mock_sb.table.return_value = FluentMock(
        select_data=[],                                           # no existing log
        write_data=[{"id": "log-id-1", "taken_at": TAKEN_AT}],  # insert result
    )

    resp = client.post("/v1/dose/confirm", json={"schedule_id": TEST_SCHEDULE_ID})

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "done"
    assert data["log_id"] == "log-id-1"
    assert data["taken_at"] == TAKEN_AT


def test_confirm_dose_updates_existing_skipped(client, mock_sb):
    """Existing 'skipped' log → update to 'done'."""
    mock_sb.table.return_value = FluentMock(
        select_data=[{"id": "log-id-1"}],                        # existing log found
        write_data=[{"id": "log-id-1", "taken_at": TAKEN_AT}],  # update result
    )

    resp = client.post("/v1/dose/confirm", json={"schedule_id": TEST_SCHEDULE_ID})

    assert resp.status_code == 201
    assert resp.json()["status"] == "done"


def test_confirm_dose_missing_schedule_id(client):
    resp = client.post("/v1/dose/confirm", json={})
    assert resp.status_code == 422


# ── POST /v1/dose/skip ────────────────────────────────────────────────────

def test_skip_dose_new_log(client, mock_sb):
    """No existing log → insert new 'skipped' record."""
    mock_sb.table.return_value = FluentMock(
        select_data=[],
        write_data=[{"id": "log-id-2", "taken_at": None}],
    )

    resp = client.post("/v1/dose/skip", json={"schedule_id": TEST_SCHEDULE_ID})

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "skipped"
    assert data["log_id"] == "log-id-2"


def test_skip_dose_updates_existing_done(client, mock_sb):
    """Existing 'done' log → update to 'skipped' and clear taken_at."""
    mock_sb.table.return_value = FluentMock(
        select_data=[{"id": "log-id-2"}],
        write_data=[{"id": "log-id-2", "taken_at": None}],
    )

    resp = client.post("/v1/dose/skip", json={"schedule_id": TEST_SCHEDULE_ID})

    assert resp.status_code == 201
    assert resp.json()["status"] == "skipped"


# ── DELETE /v1/dose/undo ──────────────────────────────────────────────────

def test_undo_dose_success(client, mock_sb):
    """Existing log found → delete it → returns deleted=True."""
    mock_sb.table.return_value = FluentMock(
        select_data=[{"id": "log-id-1"}],
        write_data=[{}],
    )

    resp = client.delete(f"/v1/dose/undo?schedule_id={TEST_SCHEDULE_ID}")

    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


def test_undo_dose_no_log_today(client, mock_sb):
    """No log for today → returns deleted=False (not an error)."""
    mock_sb.table.return_value = FluentMock(select_data=[])

    resp = client.delete(f"/v1/dose/undo?schedule_id={TEST_SCHEDULE_ID}")

    assert resp.status_code == 200
    assert resp.json()["deleted"] is False


def test_undo_dose_missing_schedule_id(client):
    resp = client.delete("/v1/dose/undo")
    assert resp.status_code == 422


# ── GET /v1/dose/logs ─────────────────────────────────────────────────────

def test_get_dose_logs_with_entries(client, mock_sb):
    mock_sb.table.side_effect = make_table({
        "medications": [
            {"id": TEST_MED_ID, "schedules": [{"id": TEST_SCHEDULE_ID, "is_active": True}]},
        ],
        "dose_logs": [
            {"log_date": "2024-01-15", "status": "done"},   # 1 done for 1 schedule → 100%
        ],
    })

    resp = client.get("/v1/dose/logs", params={"from": "2024-01-01", "to": "2024-01-31"})

    assert resp.status_code == 200
    data = resp.json()
    assert "logs" in data
    log = data["logs"][0]
    assert log["date"] == "2024-01-15"
    assert log["done"] == 1
    assert log["total"] == 1
    assert log["grade"] == "green"
    assert log["rate"] == 100


def test_get_dose_logs_empty_no_medications(client, mock_sb):
    mock_sb.table.return_value = FluentMock(select_data=[])

    resp = client.get("/v1/dose/logs", params={"from": "2024-01-01", "to": "2024-01-31"})

    assert resp.status_code == 200
    assert resp.json()["logs"] == []


def test_get_dose_logs_missing_date_params(client):
    resp = client.get("/v1/dose/logs")
    assert resp.status_code == 422


# ── GET /v1/dose/stats ────────────────────────────────────────────────────

def test_get_dose_stats_week(client, mock_sb):
    mock_sb.table.side_effect = make_table({
        "medications": [
            {
                "id": TEST_MED_ID,
                "name": "아스피린",
                "color_tag": "#1D9E75",
                "schedules": [{"id": TEST_SCHEDULE_ID}],
            }
        ],
        "dose_logs": [
            {"schedule_id": TEST_SCHEDULE_ID, "status": "done"},
            {"schedule_id": TEST_SCHEDULE_ID, "status": "done"},
            {"schedule_id": TEST_SCHEDULE_ID, "status": "skipped"},
        ],
    })

    resp = client.get("/v1/dose/stats", params={"period": "week"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["period"] == "week"
    assert "overall_rate" in data
    assert isinstance(data["overall_rate"], int)
    assert len(data["by_medication"]) == 1
    assert data["by_medication"][0]["medication_name"] == "아스피린"


def test_get_dose_stats_month(client, mock_sb):
    mock_sb.table.return_value = FluentMock(select_data=[])   # no medications

    resp = client.get("/v1/dose/stats", params={"period": "month"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["period"] == "month"
    assert data["overall_rate"] == 0
    assert data["by_medication"] == []


def test_get_dose_stats_invalid_period(client):
    resp = client.get("/v1/dose/stats", params={"period": "year"})
    assert resp.status_code == 422


# ── GET /v1/dose/logs/day ─────────────────────────────────────────────────

def test_get_day_logs_with_items(client, mock_sb):
    meds_result = [
        {"id": TEST_MED_ID, "schedules": [{"id": TEST_SCHEDULE_ID, "is_active": True}]},
    ]
    logs_result = [
        {
            "id": "log-id-1",
            "schedule_id": TEST_SCHEDULE_ID,
            "status": "done",
            "taken_at": TAKEN_AT,
            "schedules": {
                "scheduled_time": "09:00:00",
                "medications": {"name": "아스피린", "color_tag": "#1D9E75"},
            },
        }
    ]

    meds_calls = iter([
        FluentMock(select_data=meds_result),   # get active medication IDs
        FluentMock(select_data=logs_result),   # get dose logs for day
    ])
    mock_sb.table.side_effect = lambda name: next(meds_calls) if name == "medications" else FluentMock(select_data=logs_result)

    resp = client.get("/v1/dose/logs/day", params={"date": LOG_DATE})

    assert resp.status_code == 200
    data = resp.json()
    assert data["date"] == LOG_DATE
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["status"] == "done"
    assert item["medication_name"] == "아스피린"


def test_get_day_logs_empty(client, mock_sb):
    mock_sb.table.return_value = FluentMock(select_data=[])

    resp = client.get("/v1/dose/logs/day", params={"date": LOG_DATE})

    assert resp.status_code == 200
    data = resp.json()
    assert data["date"] == LOG_DATE
    assert data["items"] == []


def test_get_day_logs_missing_date(client):
    resp = client.get("/v1/dose/logs/day")
    assert resp.status_code == 422
