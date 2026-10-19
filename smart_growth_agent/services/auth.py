from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.db.models import Brand, BrandMembership, User
from smart_growth_agent.domain.enums import Role
from smart_growth_agent.domain.errors import ConflictError, ForbiddenError, NotFoundError
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.security import hash_password, verify_password
from smart_growth_agent.services.audit import record_audit


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def authenticate(self, *, email: str, password: str, brand_id: uuid.UUID) -> Principal:
        row = (
            await self.session.execute(
                select(User, BrandMembership)
                .join(BrandMembership, BrandMembership.user_id == User.id)
                .where(
                    func.lower(User.email) == email.lower(),
                    User.is_active.is_(True),
                    BrandMembership.brand_id == brand_id,
                )
            )
        ).one_or_none()
        if row is None or not verify_password(password, row.User.password_hash):
            raise ForbiddenError("invalid credentials or brand membership")
        return Principal(
            user_id=row.User.id,
            brand_id=brand_id,
            role=row.BrandMembership.role,
            email=row.User.email,
        )

    async def bootstrap_admin(
        self,
        *,
        brand_name: str,
        brand_slug: str,
        email: str,
        display_name: str,
        password: str,
    ) -> tuple[Brand, User]:
        async with self.session.begin():
            existing_users = await self.session.scalar(select(func.count()).select_from(User))
            if existing_users:
                raise ConflictError("bootstrap is disabled after the first user is created")
            brand = Brand(name=brand_name, slug=brand_slug)
            user = User(
                email=email.lower(),
                display_name=display_name,
                password_hash=hash_password(password),
            )
            self.session.add_all([brand, user])
            await self.session.flush()
            self.session.add(BrandMembership(brand_id=brand.id, user_id=user.id, role=Role.ADMIN))
        return brand, user

    async def create_member(
        self,
        *,
        brand_id: uuid.UUID,
        email: str,
        display_name: str,
        password: str,
        role: Role,
        actor_id: uuid.UUID,
    ) -> tuple[User, BrandMembership]:
        async with self.session.begin():
            existing = await self.session.scalar(
                select(User).where(func.lower(User.email) == email.lower())
            )
            if existing is not None:
                raise ConflictError("email already exists")
            user = User(
                email=email.lower(),
                display_name=display_name,
                password_hash=hash_password(password),
            )
            self.session.add(user)
            await self.session.flush()
            membership = BrandMembership(brand_id=brand_id, user_id=user.id, role=role)
            self.session.add(membership)
            await self.session.flush()
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="user.created",
                resource_type="user",
                resource_id=user.id,
                details={"role": role.value},
            )
        return user, membership

    async def reset_password(self, *, email: str, password: str) -> User:
        """Reset a local user's password from the trusted administration CLI."""
        async with self.session.begin():
            user = await self.session.scalar(
                select(User)
                .where(func.lower(User.email) == email.lower())
                .with_for_update()
            )
            if user is None:
                raise NotFoundError("user email not found")
            user.password_hash = hash_password(password)
            memberships = list(
                await self.session.scalars(
                    select(BrandMembership).where(BrandMembership.user_id == user.id)
                )
            )
            for membership in memberships:
                record_audit(
                    self.session,
                    brand_id=membership.brand_id,
                    actor_id=user.id,
                    action="user.password_reset_by_local_admin",
                    resource_type="user",
                    resource_id=user.id,
                    details={"email": user.email},
                )
        return user
