import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))

from api.main import app, db, User, Item
import json


@pytest.fixture
def client():
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


@pytest.fixture
def auth_header(client):
    user_data = {"email": "test@example.com", "password": "testpass123", "name": "Test User"}
    client.post("/api/auth/register", json=user_data)

    response = client.post(
        "/api/auth/login", json={"email": user_data["email"], "password": user_data["password"]}
    )
    token = response.get_json()["access_token"]

    return {"Authorization": f"Bearer {token}"}


class TestHealthCheck:
    def test_health_returns_healthy(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "healthy"


class TestAuthRegistration:
    def test_register_success(self, client):
        response = client.post(
            "/api/auth/register",
            json={"email": "newuser@example.com", "password": "password123", "name": "New User"},
        )
        assert response.status_code == 201
        data = response.get_json()
        assert "user" in data
        assert data["user"]["email"] == "newuser@example.com"

    def test_register_missing_email(self, client):
        response = client.post("/api/auth/register", json={"password": "password123"})
        assert response.status_code == 400

    def test_register_duplicate_email(self, client):
        user_data = {"email": "duplicate@example.com", "password": "password123"}
        client.post("/api/auth/register", json=user_data)
        response = client.post("/api/auth/register", json=user_data)
        assert response.status_code == 400


class TestAuthLogin:
    def test_login_success(self, client):
        client.post(
            "/api/auth/register", json={"email": "login@example.com", "password": "password123"}
        )

        response = client.post(
            "/api/auth/login", json={"email": "login@example.com", "password": "password123"}
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_login_invalid_credentials(self, client):
        response = client.post(
            "/api/auth/login", json={"email": "wrong@example.com", "password": "wrongpass"}
        )
        assert response.status_code == 401


class TestAuthMe:
    def test_get_current_user_success(self, client, auth_header):
        response = client.get("/api/auth/me", headers=auth_header)
        assert response.status_code == 200
        data = response.get_json()
        assert data["email"] == "test@example.com"

    def test_get_current_user_no_token(self, client):
        response = client.get("/api/auth/me")
        assert response.status_code == 401


class TestItemsCRUD:
    def test_create_item_success(self, client, auth_header):
        response = client.post(
            "/api/items",
            json={
                "name": "Test Item",
                "description": "A test item",
                "price": 29.99,
                "quantity": 10,
            },
            headers=auth_header,
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data["item"]["name"] == "Test Item"

    def test_list_items(self, client, auth_header):
        client.post("/api/items", json={"name": "Item 1", "price": 10.0}, headers=auth_header)
        client.post("/api/items", json={"name": "Item 2", "price": 20.0}, headers=auth_header)

        response = client.get("/api/items")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["items"]) == 2

    def test_get_item_by_id(self, client, auth_header):
        create_response = client.post(
            "/api/items", json={"name": "Single Item", "price": 50.0}, headers=auth_header
        )
        item_id = create_response.get_json()["item"]["id"]

        response = client.get(f"/api/items/{item_id}")
        assert response.status_code == 200
        assert response.get_json()["name"] == "Single Item"

    def test_update_item(self, client, auth_header):
        create_response = client.post(
            "/api/items", json={"name": "Original", "price": 10.0}, headers=auth_header
        )
        item_id = create_response.get_json()["item"]["id"]

        response = client.put(
            f"/api/items/{item_id}", json={"name": "Updated", "price": 20.0}, headers=auth_header
        )
        assert response.status_code == 200
        assert response.get_json()["item"]["name"] == "Updated"

    def test_partial_update_item(self, client, auth_header):
        create_response = client.post(
            "/api/items", json={"name": "Original", "price": 10.0}, headers=auth_header
        )
        item_id = create_response.get_json()["item"]["id"]

        response = client.patch(f"/api/items/{item_id}", json={"price": 99.99}, headers=auth_header)
        assert response.status_code == 200
        data = response.get_json()
        assert data["item"]["name"] == "Original"
        assert data["item"]["price"] == 99.99

    def test_delete_item(self, client, auth_header):
        create_response = client.post(
            "/api/items", json={"name": "To Delete", "price": 10.0}, headers=auth_header
        )
        item_id = create_response.get_json()["item"]["id"]

        response = client.delete(f"/api/items/{item_id}", headers=auth_header)
        assert response.status_code == 200

        get_response = client.get(f"/api/items/{item_id}")
        assert get_response.status_code == 404

    def test_create_item_unauthorized(self, client):
        response = client.post("/api/items", json={"name": "Test", "price": 10.0})
        assert response.status_code == 401


class TestPagination:
    def test_pagination(self, client, auth_header):
        for i in range(25):
            client.post(
                "/api/items", json={"name": f"Item {i}", "price": i * 10}, headers=auth_header
            )

        response = client.get("/api/items?page=1&per_page=10")
        data = response.get_json()
        assert len(data["items"]) == 10
        assert data["total"] == 25
        assert data["pages"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
