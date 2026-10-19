from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.app.dependencies import get_principal, require_permission
from smart_growth_agent.db.models import EvidenceDocument
from smart_growth_agent.db.session import get_session
from smart_growth_agent.domain.enums import RegistryType
from smart_growth_agent.repositories.registry import RegistryRepository
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.schemas.registry import (
    EvidenceDocumentCreate,
    EvidenceDocumentRead,
    RegistryItemCreate,
    RegistryItemDetail,
    RegistryItemRead,
    RegistryRevisionCreate,
    RegistryRevisionRead,
    RegistryRevisionUpdate,
)
from smart_growth_agent.services.registry import RegistryService

router = APIRouter(tags=["registry"])


@router.post(
    "/registry/{registry_type}",
    response_model=RegistryItemDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_registry_item(
    registry_type: RegistryType,
    data: RegistryItemCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("registry:write")),
) -> RegistryItemDetail:
    item, revision = await RegistryService(session).create_item(
        brand_id=principal.brand_id,
        registry_type=registry_type,
        data=data,
        actor_id=principal.user_id,
    )
    item_data = RegistryItemRead.model_validate(item).model_dump()
    return RegistryItemDetail(
        **item_data, revisions=[RegistryRevisionRead.model_validate(revision)]
    )


@router.get("/registry/{registry_type}", response_model=list[RegistryItemRead])
async def list_registry_items(
    registry_type: RegistryType,
    include_archived: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[RegistryItemRead]:
    items = await RegistryRepository(session).list_items(
        principal.brand_id,
        registry_type,
        include_archived=include_archived,
    )
    return [RegistryItemRead.model_validate(item) for item in items]


@router.get("/registry/{registry_type}/{item_id}", response_model=RegistryItemDetail)
async def get_registry_item(
    registry_type: RegistryType,
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> RegistryItemDetail:
    item, revisions = await RegistryService(session).get_item_detail(principal.brand_id, item_id)
    if item.registry_type != registry_type:
        from smart_growth_agent.domain.errors import NotFoundError

        raise NotFoundError("registry item not found")
    item_data = RegistryItemRead.model_validate(item).model_dump()
    return RegistryItemDetail(
        **item_data,
        revisions=[RegistryRevisionRead.model_validate(revision) for revision in revisions],
    )


@router.post(
    "/registry/{registry_type}/{item_id}/revisions",
    response_model=RegistryRevisionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_registry_revision(
    registry_type: RegistryType,
    item_id: uuid.UUID,
    data: RegistryRevisionCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("registry:write")),
) -> RegistryRevisionRead:
    revision = await RegistryService(session).create_revision(
        brand_id=principal.brand_id,
        item_id=item_id,
        data=data,
        actor_id=principal.user_id,
        expected_type=registry_type,
    )
    return RegistryRevisionRead.model_validate(revision)


@router.patch(
    "/registry/{registry_type}/{item_id}/revisions/{revision_id}",
    response_model=RegistryRevisionRead,
)
async def update_registry_revision(
    registry_type: RegistryType,
    item_id: uuid.UUID,
    revision_id: uuid.UUID,
    data: RegistryRevisionUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("registry:write")),
) -> RegistryRevisionRead:
    revision = await RegistryService(session).update_revision(
        brand_id=principal.brand_id,
        revision_id=revision_id,
        data=data,
        actor_id=principal.user_id,
        expected_type=registry_type,
    )
    if revision.item_id != item_id:
        from smart_growth_agent.domain.errors import NotFoundError

        raise NotFoundError("registry revision not found")
    return RegistryRevisionRead.model_validate(revision)


@router.post(
    "/registry/{registry_type}/{item_id}/revisions/{revision_id}/activate",
    response_model=RegistryRevisionRead,
)
async def activate_registry_revision(
    registry_type: RegistryType,
    item_id: uuid.UUID,
    revision_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("registry:activate")),
) -> RegistryRevisionRead:
    revision = await RegistryService(session).activate_revision(
        brand_id=principal.brand_id,
        revision_id=revision_id,
        actor_id=principal.user_id,
        expected_type=registry_type,
    )
    if revision.item_id != item_id:
        from smart_growth_agent.domain.errors import NotFoundError

        raise NotFoundError("registry revision not found")
    return RegistryRevisionRead.model_validate(revision)


@router.post(
    "/registry/{registry_type}/{item_id}/revisions/{revision_id}/retire",
    response_model=RegistryRevisionRead,
)
async def retire_registry_revision(
    registry_type: RegistryType,
    item_id: uuid.UUID,
    revision_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("registry:activate")),
) -> RegistryRevisionRead:
    revision = await RegistryService(session).retire_revision(
        brand_id=principal.brand_id,
        revision_id=revision_id,
        actor_id=principal.user_id,
        expected_type=registry_type,
    )
    if revision.item_id != item_id:
        from smart_growth_agent.domain.errors import NotFoundError

        raise NotFoundError("registry revision not found")
    return RegistryRevisionRead.model_validate(revision)


@router.post(
    "/registry/{registry_type}/{item_id}/archive",
    response_model=RegistryItemRead,
)
async def archive_registry_item(
    registry_type: RegistryType,
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("registry:write")),
) -> RegistryItemRead:
    item = await RegistryService(session).set_item_archived(
        brand_id=principal.brand_id,
        item_id=item_id,
        archived=True,
        actor_id=principal.user_id,
        expected_type=registry_type,
    )
    return RegistryItemRead.model_validate(item)


@router.post(
    "/registry/{registry_type}/{item_id}/restore",
    response_model=RegistryItemRead,
)
async def restore_registry_item(
    registry_type: RegistryType,
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("registry:write")),
) -> RegistryItemRead:
    item = await RegistryService(session).set_item_archived(
        brand_id=principal.brand_id,
        item_id=item_id,
        archived=False,
        actor_id=principal.user_id,
        expected_type=registry_type,
    )
    return RegistryItemRead.model_validate(item)


@router.delete(
    "/registry/{registry_type}/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def permanently_delete_registry_item(
    registry_type: RegistryType,
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("assets:delete")),
) -> None:
    await RegistryService(session).permanently_delete_item(
        brand_id=principal.brand_id,
        item_id=item_id,
        actor_id=principal.user_id,
        expected_type=registry_type,
    )


@router.post(
    "/evidence",
    response_model=EvidenceDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_evidence_document(
    data: EvidenceDocumentCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("registry:write")),
) -> EvidenceDocumentRead:
    document = await RegistryService(session).create_evidence(
        brand_id=principal.brand_id, data=data, actor_id=principal.user_id
    )
    return EvidenceDocumentRead.model_validate(document)


@router.get("/evidence", response_model=list[EvidenceDocumentRead])
async def list_evidence_documents(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[EvidenceDocumentRead]:
    documents = list(
        await session.scalars(
            select(EvidenceDocument)
            .where(EvidenceDocument.brand_id == principal.brand_id)
            .order_by(EvidenceDocument.created_at.desc())
        )
    )
    return [EvidenceDocumentRead.model_validate(document) for document in documents]


@router.post("/evidence/{document_id}/verify", response_model=EvidenceDocumentRead)
async def verify_evidence_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("registry:activate")),
) -> EvidenceDocumentRead:
    document = await RegistryService(session).verify_evidence(
        brand_id=principal.brand_id,
        document_id=document_id,
        actor_id=principal.user_id,
    )
    return EvidenceDocumentRead.model_validate(document)
