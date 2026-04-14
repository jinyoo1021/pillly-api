"""Integration tests for system endpoints."""


def test_health_check(anon_client):
    resp = anon_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
