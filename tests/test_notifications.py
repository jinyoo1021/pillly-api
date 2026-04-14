"""
Integration tests for /v1/notifications/* endpoints.

firebase_admin.messaging is already a MagicMock (injected via sys.modules in conftest.py),
so FCM send calls succeed silently without network access.

QStash signature verification is skipped when QSTASH_CURRENT_SIGNING_KEY == "local-dummy"
(the test default), so webhook tests can call /notify without a real HMAC signature.
"""

from tests.conftest import FluentMock, make_table, TEST_USER_ID, TEST_MED_ID, TEST_SCHEDULE_ID


# ── POST /v1/notifications/token ─────────────────────────────────────────

def test_register_device_token_android(client, mock_sb):
    mock_sb.table.return_value = FluentMock(write_data=[{}])

    resp = client.post("/v1/notifications/token", json={
        "token": "fcm-device-token-abc123",
        "platform": "android",
    })

    assert resp.status_code == 200
    assert resp.json()["registered"] is True


def test_register_device_token_ios(client, mock_sb):
    mock_sb.table.return_value = FluentMock(write_data=[{}])

    resp = client.post("/v1/notifications/token", json={
        "token": "apns-device-token-xyz",
        "platform": "ios",
    })

    assert resp.status_code == 200
    assert resp.json()["registered"] is True


def test_register_device_token_missing_fields(client):
    resp = client.post("/v1/notifications/token", json={"token": "fcm-token"})
    assert resp.status_code == 422


# ── POST /v1/notifications/notify (QStash webhook) ───────────────────────

def test_notify_webhook_sends_fcm(anon_client, mock_sb):
    """Full push flow for an Android device — FCM send must be called."""
    import firebase_admin.messaging as messaging   # this is our MagicMock

    mock_sb.table.side_effect = make_table({
        "schedules": FluentMock(select_data={
            "id": TEST_SCHEDULE_ID,
            "medication_id": TEST_MED_ID,
            "cycle_type": "daily",
            "cycle_value": None,
            "scheduled_time": "09:00:00",
        }),
        "medications": FluentMock(select_data={"name": "아스피린", "is_active": True}),
        "device_tokens": FluentMock(select_data=[{"token": "fcm-token-abc", "platform": "android"}]),
        "notification_logs": FluentMock(write_data=[{}]),
    })

    resp = anon_client.post("/v1/notifications/notify", json={
        "schedule_id": TEST_SCHEDULE_ID,
        "user_id": TEST_USER_ID,
    })

    assert resp.status_code == 200
    assert resp.json()["sent"] is True
    assert resp.json()["platform"] == "android"
    messaging.send.assert_called_once()


def test_notify_webhook_skips_when_no_device_token(anon_client, mock_sb):
    mock_sb.table.side_effect = make_table({
        "schedules": FluentMock(select_data={
            "id": TEST_SCHEDULE_ID,
            "medication_id": TEST_MED_ID,
            "cycle_type": "daily",
            "cycle_value": None,
            "scheduled_time": "09:00:00",
        }),
        "medications": FluentMock(select_data={"name": "아스피린", "is_active": True}),
        "device_tokens": FluentMock(select_data=[]),    # no token registered
        "notification_logs": FluentMock(write_data=[{}]),
    })

    resp = anon_client.post("/v1/notifications/notify", json={
        "schedule_id": TEST_SCHEDULE_ID,
        "user_id": TEST_USER_ID,
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["sent"] is False
    assert data["reason"] == "NO_DEVICE_TOKEN"


def test_notify_webhook_skips_inactive_medication(anon_client, mock_sb):
    mock_sb.table.side_effect = make_table({
        "schedules": FluentMock(select_data={
            "id": TEST_SCHEDULE_ID,
            "medication_id": TEST_MED_ID,
            "cycle_type": "daily",
            "cycle_value": None,
            "scheduled_time": "09:00:00",
        }),
        "medications": FluentMock(select_data={"name": "아스피린", "is_active": False}),  # inactive
        "notification_logs": FluentMock(write_data=[{}]),
    })

    resp = anon_client.post("/v1/notifications/notify", json={
        "schedule_id": TEST_SCHEDULE_ID,
        "user_id": TEST_USER_ID,
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["sent"] is False
    assert data["reason"] == "MEDICATION_INACTIVE"


def test_notify_webhook_interval_skips_non_matching_day(anon_client, mock_sb):
    """
    Interval schedules fire daily via QStash but server filters non-matching days.
    Simulate a case where today doesn't match the interval.
    """
    from datetime import date, timedelta

    # start_date: yesterday; interval: 3 days → today (day 1) is NOT a match
    start_date = (date.today() - timedelta(days=1)).isoformat()

    mock_sb.table.side_effect = make_table({
        "schedules": FluentMock(select_data={
            "id": TEST_SCHEDULE_ID,
            "medication_id": TEST_MED_ID,
            "cycle_type": "interval",
            "cycle_value": {"days": 3, "start_date": start_date},
            "scheduled_time": "09:00:00",
        }),
    })

    resp = anon_client.post("/v1/notifications/notify", json={
        "schedule_id": TEST_SCHEDULE_ID,
        "user_id": TEST_USER_ID,
    })

    assert resp.status_code == 200
    assert resp.json()["sent"] is False
    assert resp.json()["reason"] == "INTERVAL_NOT_TODAY"


# ── GET /v1/notifications/log ─────────────────────────────────────────────

def test_get_notification_log_empty(client, mock_sb):
    mock_sb.table.return_value = FluentMock(select_data=[])

    resp = client.get("/v1/notifications/log")

    assert resp.status_code == 200
    assert resp.json() == {"logs": []}


def test_get_notification_log_with_entries(client, mock_sb):
    logs_data = [
        {
            "schedule_id": TEST_SCHEDULE_ID,
            "sent_at": "2024-01-15T09:00:00+00:00",
            "status": "delivered",
            "snooze_count": 0,
        }
    ]

    call_counts = {"n": 0}

    def _table(name):
        if name == "notification_logs":
            return FluentMock(select_data=logs_data)
        if name == "schedules":
            return FluentMock(select_data=[{"medication_id": TEST_MED_ID}])
        if name == "medications":
            return FluentMock(select_data=[{"name": "아스피린"}])
        return FluentMock()

    mock_sb.table.side_effect = _table

    resp = client.get("/v1/notifications/log")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["logs"]) == 1
    log = data["logs"][0]
    assert log["status"] == "delivered"
    assert log["medication_name"] == "아스피린"
    assert log["snooze_count"] == 0
