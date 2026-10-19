from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.fernet import Fernet, InvalidToken
from pwdlib import PasswordHash

from smart_growth_agent.config import Settings
from smart_growth_agent.domain.enums import Role
from smart_growth_agent.schemas.auth import Principal

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_access_token(principal: Principal, settings: Settings) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_minutes)
    payload: dict[str, Any] = {
        "sub": str(principal.user_id),
        "brand_id": str(principal.brand_id),
        "role": principal.role.value,
        "email": principal.email,
        "iat": datetime.now(UTC),
        "exp": expires_at,
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_at


def decode_access_token(token: str, settings: Settings) -> Principal:
    payload = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )
    return Principal(
        user_id=uuid.UUID(payload["sub"]),
        brand_id=uuid.UUID(payload["brand_id"]),
        role=Role(payload["role"]),
        email=payload["email"],
    )


ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.ADMIN: {
        "users:manage",
        "registry:write",
        "registry:activate",
        "brief:write",
        "run:write",
        "analytics:write",
        "assets:delete",
        "review",
        "llm:manage",
        "audit:read",
    },
    Role.EDITOR: {"registry:write", "brief:write", "run:write", "analytics:write"},
    Role.REVIEWER: {"registry:activate", "review"},
}


def role_allows(role: Role, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS[role]


class CredentialCipher:
    def __init__(self, settings: Settings) -> None:
        if settings.credential_encryption_key is None:
            raise RuntimeError("credential encryption key is not configured")
        material = settings.credential_encryption_key.get_secret_value().encode()
        key = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
        self._fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise RuntimeError("stored credential cannot be decrypted") from exc
