import hashlib
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from google.auth import exceptions as google_errors
from sqlalchemy import delete, event
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, SQLModel, create_engine

from .chat import create_router
from .google import verify_credential
from .models import BrowserSession, GoogleChallenge, GoogleCredential, User, UserProfile

COOKIE_PATH = "/api/auth"
SESSION_COOKIE = "kett_session"
CHALLENGE_COOKIE = "kett_google_challenge"
SESSION_LIFETIME = 7 * 24 * 60 * 60
CHALLENGE_LIFETIME = 10 * 60
DEFAULT_DATABASE = (
    f"sqlite:///{(Path(__file__).resolve().parents[1] / 'kett.sqlite3').as_posix()}"
)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_app(
    *,
    database_url: str | None = None,
    google_client_id: str | None = None,
    app_origin: str | None = None,
    http_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    client_id = (
        google_client_id
        if google_client_id is not None
        else os.getenv("GOOGLE_CLIENT_ID", "")
    ).strip()
    origin = (
        (app_origin or os.getenv("APP_ORIGIN", "http://localhost:5173"))
        .strip()
        .rstrip("/")
    )
    db_url = database_url or os.getenv("DATABASE_URL") or DEFAULT_DATABASE
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        SQLModel.metadata.create_all(engine)
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="Kett API", lifespan=lifespan)
    cookie_options = {
        "path": COOKIE_PATH,
        "httponly": True,
        "samesite": "lax",
        "secure": origin.startswith("https://"),
    }

    def get_db():
        with Session(engine) as db:
            yield db

    def require_same_origin(request: Request):
        # Cookie-authenticated writes must come from the configured web app.
        if request.headers.get("origin") != origin:
            raise HTTPException(403, "Untrusted origin")

    def require_google():
        if not client_id:
            raise HTTPException(503, "Google sign-in is not configured")

    @app.middleware("http")
    async def disable_auth_cache(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(f"{COOKIE_PATH}/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def revoke_cookie_session(db: Session, request: Request, cookie_name: str):
        if token := request.cookies.get(cookie_name):
            row = BrowserSession.user_id
            kind = (
                row.is_(None) if cookie_name == CHALLENGE_COOKIE else row.is_not(None)
            )
            db.execute(
                delete(BrowserSession).where(
                    BrowserSession.token_hash == token_hash(token), kind
                )
            )

    def current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            session = db.get(BrowserSession, token_hash(token))
            if (
                session
                and session.user_id is not None
                and session.expires_at > time.time()
                and (user := db.get(User, session.user_id))
            ):
                return user
        raise HTTPException(401, "Not signed in")

    @app.post(
        f"{COOKIE_PATH}/google/challenge",
        dependencies=[Depends(require_same_origin), Depends(require_google)],
    )
    def google_challenge(
        request: Request, response: Response, db: Annotated[Session, Depends(get_db)]
    ) -> GoogleChallenge:
        now = int(time.time())
        db.execute(delete(BrowserSession).where(BrowserSession.expires_at <= now))
        revoke_cookie_session(db, request, CHALLENGE_COOKIE)
        secret = secrets.token_urlsafe(32)
        nonce = token_hash(secret)
        db.add(BrowserSession(token_hash=nonce, expires_at=now + CHALLENGE_LIFETIME))
        db.commit()
        response.set_cookie(
            CHALLENGE_COOKIE, secret, max_age=CHALLENGE_LIFETIME, **cookie_options
        )
        return GoogleChallenge(nonce=nonce)

    @app.post(
        f"{COOKIE_PATH}/google",
        response_model=UserProfile,
        dependencies=[Depends(require_same_origin), Depends(require_google)],
    )
    def google_sign_in(
        payload: GoogleCredential,
        request: Request,
        response: Response,
        db: Annotated[Session, Depends(get_db)],
    ) -> User:
        challenge_secret = request.cookies.get(CHALLENGE_COOKIE)
        if not challenge_secret:
            raise HTTPException(401, "Missing sign-in challenge")
        nonce = token_hash(challenge_secret)
        try:
            claims = verify_credential(payload.credential, client_id)
        except google_errors.TransportError:
            raise HTTPException(
                503, "Could not reach Google to verify sign-in"
            ) from None
        except (ValueError, google_errors.GoogleAuthError):
            raise HTTPException(401, "Invalid Google credential") from None

        subject = claims.get("sub")
        if (
            not isinstance(subject, str)
            or not 1 <= len(subject) <= 255
            or claims.get("nonce") != nonce
            or claims.get("azp", client_id) != client_id
        ):
            raise HTTPException(401, "Invalid Google credential")

        now = int(time.time())
        # Consume the challenge in the same transaction that creates the login.
        consumed = db.execute(
            delete(BrowserSession).where(
                BrowserSession.token_hash == nonce,
                BrowserSession.user_id.is_(None),
                BrowserSession.expires_at > now,
            )
        )
        if consumed.rowcount != 1:
            raise HTTPException(401, "Invalid or expired sign-in challenge")

        name = claims.get("name")
        name = (name.strip()[:255] if isinstance(name, str) else "") or "Google account"
        email = claims.get("email")
        if (
            claims.get("email_verified") is not True
            or not isinstance(email, str)
            or not 1 <= len(email) <= 320
        ):
            email = None
        # Match accounts by Google's stable subject, never by email or name.
        upsert = insert(User).values(google_sub=subject, name=name, email=email)
        user = db.scalars(
            upsert.on_conflict_do_update(
                index_elements=[User.google_sub], set_={"name": name, "email": email}
            ).returning(User)
        ).one()

        revoke_cookie_session(db, request, SESSION_COOKIE)
        secret = secrets.token_urlsafe(32)
        db.add(
            BrowserSession(
                token_hash=token_hash(secret),
                user_id=user.id,
                expires_at=now + SESSION_LIFETIME,
            )
        )
        db.commit()
        db.refresh(user)
        response.delete_cookie(CHALLENGE_COOKIE, **cookie_options)
        response.set_cookie(
            SESSION_COOKIE, secret, max_age=SESSION_LIFETIME, **cookie_options
        )
        return user

    @app.get(f"{COOKIE_PATH}/me", response_model=UserProfile)
    def get_me(user: Annotated[User, Depends(current_user)]) -> User:
        return user

    @app.post(
        f"{COOKIE_PATH}/logout",
        status_code=204,
        dependencies=[Depends(require_same_origin)],
    )
    def logout(
        request: Request, response: Response, db: Annotated[Session, Depends(get_db)]
    ):
        revoke_cookie_session(db, request, SESSION_COOKIE)
        revoke_cookie_session(db, request, CHALLENGE_COOKIE)
        db.commit()
        response.delete_cookie(SESSION_COOKIE, **cookie_options)
        response.delete_cookie(CHALLENGE_COOKIE, **cookie_options)

    app.include_router(create_router(require_same_origin, http_transport))
    return app


app = create_app()
