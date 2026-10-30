"""API authentication and role-based authorization regression tests."""

import pytest
from fastapi.testclient import TestClient

from api.main import app, db_session as api_db_session
from database.schema import User
from services.auth_service import AuthService


@pytest.fixture
def api_client(db_session):
    def override_db_session():
        yield db_session

    app.dependency_overrides[api_db_session] = override_db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(api_db_session, None)


def create_user(db_session, username, role):
    return AuthService.create_user(
        db=db_session,
        username=username,
        email=f"{username}@test.local",
        password="TestPassword123!",
        role=role,
    )


def login(client, username):
    response = client.post(
        "/api/auth/login",
        json={"username_or_email": username, "password": "TestPassword123!"},
    )
    assert response.status_code == 200
    return response.json()


def test_user_listing_requires_authentication(api_client):
    response = api_client.get("/api/users")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_issues_token_and_analyst_permissions_are_enforced(api_client, db_session):
    create_user(db_session, "analyst", "analyst")

    login_response = login(api_client, "analyst")
    headers = {"Authorization": f"Bearer {login_response['access_token']}"}

    assert login_response["token_type"] == "bearer"
    assert "view_dashboard" in login_response["permissions"]
    assert api_client.get("/api/tasks", headers=headers).status_code == 200
    assert api_client.get("/api/users", headers=headers).status_code == 403


def test_admin_can_list_users(api_client, db_session):
    create_user(db_session, "admin", "admin")
    login_response = login(api_client, "admin")
    headers = {"Authorization": f"Bearer {login_response['access_token']}"}

    response = api_client.get("/api/users", headers=headers)

    assert response.status_code == 200
    assert any(user["username"] == "admin" for user in response.json())


def test_deactivated_user_token_is_rejected(api_client, db_session):
    create_user(db_session, "manager", "manager")
    login_response = login(api_client, "manager")
    headers = {"Authorization": f"Bearer {login_response['access_token']}"}
    user = db_session.query(User).filter(User.username == "manager").one()
    user.is_active = False
    db_session.commit()

    response = api_client.get("/api/tasks", headers=headers)

    assert response.status_code == 401


def test_legacy_password_hash_is_upgraded_on_successful_login(db_session):
    legacy_hash, legacy_salt = AuthService.hash_password("LegacyPassword123!")
    user = User(
        username="legacy",
        email="legacy@test.local",
        hashed_password=legacy_hash,
        salt=legacy_salt.split("$")[-1],
        role="analyst",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    user.hashed_password = __import__("hashlib").sha256(
        (user.salt + "LegacyPassword123!").encode("utf-8")
    ).hexdigest()
    db_session.commit()

    assert AuthService.authenticate_user(db_session, "legacy", "LegacyPassword123!") is user
    assert user.salt.startswith("pbkdf2_sha256$")