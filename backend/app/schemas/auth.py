from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.security import BCRYPT_MAX_BYTES


def _check_password(value: str) -> str:
    if len(value) < 10:
        raise ValueError("Password must be at least 10 characters")
    if len(value.encode()) > BCRYPT_MAX_BYTES:
        raise ValueError(f"Password must be at most {BCRYPT_MAX_BYTES} bytes")
    if value.lower() == value or value.upper() == value or not any(c.isdigit() for c in value):
        raise ValueError("Password must mix upper- and lower-case letters and include a digit")
    return value


class RegisterRequest(BaseModel):
    """Self-service sign-up. Exactly one of:
      * organization_name — create a new organization; caller becomes its admin
      * join_slug — join an existing organization's service portal as a requester
        (only when that organization enabled portal sign-up)
    Role and tenant are never caller-supplied."""

    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str
    organization_name: str | None = Field(default=None, min_length=2, max_length=120)
    join_slug: str | None = Field(default=None, max_length=80)

    _password = field_validator("password")(_check_password)

    @model_validator(mode="after")
    def _one_target(self):
        if bool(self.organization_name) == bool(self.join_slug):
            raise ValueError("Provide either organization_name (new organization) or join_slug (join a portal)")
        return self


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 -- OAuth2 token type, not a secret
    expires_in: int


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class EmailIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str

    _password = field_validator("new_password")(_check_password)


class AcceptInvitationIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    name: str = Field(min_length=1, max_length=120)
    password: str

    _password = field_validator("password")(_check_password)


class InvitationPreviewOut(BaseModel):
    organization_name: str
    email: str
    role: str
    invited_by: str


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str

    _password = field_validator("new_password")(_check_password)
