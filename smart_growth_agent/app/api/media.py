from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.app.dependencies import get_principal, require_permission
from smart_growth_agent.config import Settings, get_settings
from smart_growth_agent.db.models import ProductMediaAsset
from smart_growth_agent.db.session import SessionFactory, get_session
from smart_growth_agent.domain.errors import NotFoundError
from smart_growth_agent.schemas.auth import Principal
from smart_growth_agent.schemas.media import ProductMediaRead
from smart_growth_agent.services.media import MAX_IMAGE_BYTES, ProductMediaService

router = APIRouter(prefix="/product-media", tags=["product-media"])
public_router = APIRouter(tags=["product-media-preview"])


def _read(asset: ProductMediaAsset) -> ProductMediaRead:
    return ProductMediaRead(
        **ProductMediaRead.model_validate(asset).model_dump(exclude={"url"}),
        url=f"/product-media/{asset.id}",
    )


@router.get("", response_model=list[ProductMediaRead])
async def list_product_media(
    product_item_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[ProductMediaRead]:
    query = select(ProductMediaAsset).where(ProductMediaAsset.brand_id == principal.brand_id)
    if product_item_id is not None:
        query = query.where(ProductMediaAsset.product_item_id == product_item_id)
    rows = list(
        await session.scalars(
            query.order_by(ProductMediaAsset.is_primary.desc(), ProductMediaAsset.created_at)
        )
    )
    return [_read(row) for row in rows]


@router.post("", response_model=ProductMediaRead, status_code=status.HTTP_201_CREATED)
async def upload_product_media(
    product_item_id: uuid.UUID = Form(),
    alt_text: str = Form(min_length=1, max_length=500),
    is_primary: bool = Form(default=False),
    file: UploadFile = File(),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(require_permission("registry:write")),
) -> ProductMediaRead:
    content = await file.read(MAX_IMAGE_BYTES + 1)
    asset = await ProductMediaService(session, settings).create(
        brand_id=principal.brand_id,
        product_item_id=product_item_id,
        file_name=file.filename or "product-image",
        content=content,
        alt_text=alt_text,
        is_primary=is_primary,
        actor_id=principal.user_id,
    )
    return _read(asset)


@router.post("/{asset_id}/primary", response_model=ProductMediaRead)
async def make_product_media_primary(
    asset_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(require_permission("registry:write")),
) -> ProductMediaRead:
    asset = await ProductMediaService(session, settings).make_primary(
        brand_id=principal.brand_id,
        asset_id=asset_id,
        actor_id=principal.user_id,
    )
    return _read(asset)


@public_router.get("/product-media/{asset_id}", include_in_schema=False)
async def product_media_file(
    asset_id: uuid.UUID,
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    async with SessionFactory() as session:
        asset = await session.get(ProductMediaAsset, asset_id)
        if asset is None:
            raise NotFoundError("product media not found")
        path = ProductMediaService(session, settings).resolve(asset.storage_key)
    return FileResponse(path, media_type=asset.mime_type)
