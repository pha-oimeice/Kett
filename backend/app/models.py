from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    google_sub: str = Field(unique=True, max_length=255)
    name: str = Field(max_length=255)
    email: str | None = Field(default=None, max_length=320)


class BrowserSession(SQLModel, table=True):
    __tablename__ = "browser_sessions"

    token_hash: str = Field(primary_key=True, max_length=64)
    # An anonymous row is a single-use Google sign-in challenge.
    user_id: int | None = Field(
        default=None, foreign_key="users.id", ondelete="CASCADE"
    )
    expires_at: int = Field(index=True)


class UserProfile(SQLModel):
    id: int
    name: str
    email: str | None


class GoogleCredential(SQLModel):
    credential: str = Field(min_length=1, max_length=8192)


class GoogleChallenge(SQLModel):
    nonce: str
