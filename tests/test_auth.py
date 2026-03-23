from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    """Verify server is running"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_register_missing_fields():
    """Register should fail without required fields"""
    response = client.post("/v1/auth/register", json={})
    assert response.status_code == 422


def test_login_missing_fields():
    """Login should fail without required fields"""
    response = client.post("/v1/auth/login", json={})
    assert response.status_code == 422


def test_register_invalid_email():
    """Register should fail with invalid email format"""
    response = client.post("/v1/auth/register", json={
        "email": "not-an-email",
        "password": "password123",
        "name": "Test User",
    })
    assert response.status_code == 422