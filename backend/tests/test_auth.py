import json
import time
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from google.auth import crypt, jwt
from google.auth.transport.requests import Request as GoogleRequest

from app import main

ORIGIN = "https://kett.example"
CLIENT_ID = "test.apps.googleusercontent.com"
AUTH = "/api/auth"


@pytest.fixture
def database_url(tmp_path):
    return f"sqlite:///{(tmp_path / 'test.sqlite3').as_posix()}"


def make_client(database_url, client_id=CLIENT_ID):
    return TestClient(
        main.create_app(
            database_url=database_url, google_client_id=client_id, app_origin=ORIGIN
        ),
        base_url=ORIGIN,
        headers={"Origin": ORIGIN},
    )


@pytest.fixture
def client(database_url):
    with make_client(database_url) as client:
        yield client


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def credential(signing_key, monkeypatch):
    def public_keys(*args, **kwargs):
        pem = signing_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return SimpleNamespace(
            status=200, data=json.dumps({"test-key": pem.decode()}).encode()
        )

    # Keep Google's actual signature and claims verifier in the request path.
    monkeypatch.setattr(GoogleRequest, "__call__", public_keys)

    def issue(nonce, /, *, key=signing_key, **overrides):
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com",
            "aud": CLIENT_ID,
            "iat": now - 1,
            "exp": now + 600,
            "sub": "google-123",
            "nonce": nonce,
            "name": "Google User",
            "email": "user@example.com",
            "email_verified": True,
        } | overrides
        signer = crypt.RSASigner(key, "test-key")
        return jwt.encode(signer, claims).decode()

    return issue


def challenge(client):
    response = client.post(f"{AUTH}/google/challenge")
    assert response.status_code == 200, response.text
    return response.json()["nonce"]


def login(client, token):
    return client.post(f"{AUTH}/google", json={"credential": token})


def test_session_and_user_survive_restart_and_logout_revokes_session(
    database_url, credential
):
    with make_client(database_url) as client:
        assert client.get(f"{AUTH}/me").status_code == 401
        nonce = challenge(client)
        challenge_cookie = client.cookies[main.CHALLENGE_COOKIE]
        token = credential(nonce)
        response = login(client, token)
        assert response.status_code == 200, response.text
        profile = response.json()
        assert profile == {"id": 1, "name": "Google User", "email": "user@example.com"}
        cookie_header = next(
            value
            for value in response.headers.get_list("set-cookie")
            if value.startswith(f"{main.SESSION_COOKIE}=")
        )
        assert all(
            flag in cookie_header for flag in ("HttpOnly", "Secure", "SameSite=lax")
        )
        assert response.headers["cache-control"] == "no-store"
        session_cookie = client.cookies[main.SESSION_COOKIE]
        client.cookies.set(main.CHALLENGE_COOKIE, challenge_cookie)
        assert login(client, token).status_code == 401  # Challenge is single-use.

    with make_client(database_url) as client:
        client.cookies.set(main.SESSION_COOKIE, session_cookie)
        assert client.get(f"{AUTH}/me").json() == profile
        assert (
            client.post(
                f"{AUTH}/logout", headers={"Origin": "https://other.example"}
            ).status_code
            == 403
        )
        assert client.get(f"{AUTH}/me").json() == profile
        assert client.post(f"{AUTH}/logout").status_code == 204
        client.cookies.set(main.SESSION_COOKIE, session_cookie)
        assert client.get(f"{AUTH}/me").status_code == 401
        client.cookies.clear()

        response = login(
            client, credential(challenge(client), name="Updated", email_verified=False)
        )
        assert response.json() == {
            "id": profile["id"],
            "name": "Updated",
            "email": None,
        }
        response = login(client, credential(challenge(client), sub="other-google-user"))
        assert response.json()["id"] != profile["id"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "other-client"},
        {"iss": "https://other.example"},
        {"iat": 100, "exp": 200},
        {"nonce": "different-nonce"},
    ],
)
def test_rejects_invalid_google_claims(client, credential, overrides):
    assert login(client, credential(challenge(client), **overrides)).status_code == 401
    assert client.get(f"{AUTH}/me").status_code == 401


def test_rejects_invalid_signature_and_missing_challenge(client, credential):
    assert login(client, credential("no-challenge")).status_code == 401
    nonce = challenge(client)
    fake_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert login(client, credential(nonce, key=fake_key)).status_code == 401
    assert login(client, "not-a-google-id-token").status_code == 401
    assert client.get(f"{AUTH}/me").status_code == 401


def test_session_and_challenge_expire(client, credential, monkeypatch):
    assert login(client, credential(challenge(client))).status_code == 200
    nonce = challenge(client)
    token = credential(nonce)
    later = time.time() + main.SESSION_LIFETIME + 1
    # Advance the application clock, independent of Google's JWT validation.
    monkeypatch.setattr(main, "time", SimpleNamespace(time=lambda: later))
    assert login(client, token).status_code == 401
    assert client.get(f"{AUTH}/me").status_code == 401


def test_cannot_start_a_challenge_without_trusted_origin_or_google_config(database_url):
    with make_client(database_url) as client:
        assert (
            client.post(
                f"{AUTH}/google/challenge", headers={"Origin": "null"}
            ).status_code
            == 403
        )
    with make_client(database_url, client_id="") as client:
        assert client.post(f"{AUTH}/google/challenge").status_code == 503
        assert client.get(f"{AUTH}/me").status_code == 401
