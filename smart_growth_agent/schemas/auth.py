from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from smart_growth_agent.domain.enums import Role


class TokenRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    brand_id: uuid.UUID


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class LoginContext(BaseModel):
    brand_id: uuid.UUID | None
    brand_name: str | None
    requires_brand_id: bool


class Principal(BaseModel):
    user_id: uuid.UUID
    brand_id: uuid.UUID
    role: Role
    email: str


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    brand_id: uuid.UUID
    role: Role


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=200)
    role: Role
