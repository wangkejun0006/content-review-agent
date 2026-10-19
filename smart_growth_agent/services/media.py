from __future__ import annotations

import io
import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from smart_growth_agent.config import Settings
from smart_growth_agent.db.models import ProductMediaAsset, RegistryItem
from smart_growth_agent.domain.enums import RegistryType
from smart_growth_agent.domain.errors import NotFoundError, ValidationError
from smart_growth_agent.services.audit import record_audit

ALLOWED_IMAGE_FORMATS = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
}
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000


class ProductMediaService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.root = settings.media_storage_path.resolve()

    @staticmethod
    def inspect_image(content: bytes) -> tuple[str, str, int, int]:
        if len(content) > MAX_IMAGE_BYTES:
            raise ValidationError("图片不能超过 15 MB")
        try:
            with Image.open(io.BytesIO(content)) as image:
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                image_format = image.format or ""
                width, height = image.size
        except (UnidentifiedImageError, OSError) as exc:
            raise ValidationError("文件不是有效的 JPG、PNG 或 WebP 图片") from exc
        if image_format not in ALLOWED_IMAGE_FORMATS:
            raise ValidationError("只支持 JPG、PNG 或 WebP 图片")
        if width * height > MAX_IMAGE_PIXELS:
            raise ValidationError("图片像素尺寸过大")
        suffix, mime_type = ALLOWED_IMAGE_FORMATS[image_format]
        return suffix, mime_type, width, height

    async def create(
        self,
        *,
        brand_id: uuid.UUID,
        product_item_id: uuid.UUID,
        file_name: str,
        content: bytes,
        alt_text: str,
        is_primary: bool,
        actor_id: uuid.UUID,
    ) -> ProductMediaAsset:
        suffix, mime_type, width, height = self.inspect_image(content)
        asset_id = uuid.uuid4()
        storage_key = f"{brand_id}/{product_item_id}/{asset_id}{suffix}"
        target = (self.root / storage_key).resolve()
        if not target.is_relative_to(self.root):
            raise ValidationError("invalid media storage path")
        try:
            async with self.session.begin():
                product = await self.session.scalar(
                    select(RegistryItem).where(
                        RegistryItem.id == product_item_id,
                        RegistryItem.brand_id == brand_id,
                        RegistryItem.registry_type == RegistryType.PRODUCT,
                    )
                )
                if product is None:
                    raise NotFoundError("product not found")
                existing_count = len(
                    list(
                        await self.session.scalars(
                            select(ProductMediaAsset.id).where(
                                ProductMediaAsset.product_item_id == product_item_id,
                                ProductMediaAsset.brand_id == brand_id,
                            )
                        )
                    )
                )
                make_primary = is_primary or existing_count == 0
                if make_primary:
                    await self.session.execute(
                        update(ProductMediaAsset)
                        .where(
                            ProductMediaAsset.product_item_id == product_item_id,
                            ProductMediaAsset.brand_id == brand_id,
                        )
                        .values(is_primary=False)
                    )
                asset = ProductMediaAsset(
                    id=asset_id,
                    brand_id=brand_id,
                    product_item_id=product_item_id,
                    file_name=file_name[:300],
                    storage_key=storage_key,
                    mime_type=mime_type,
                    byte_size=len(content),
                    width=width,
                    height=height,
                    alt_text=alt_text,
                    is_primary=make_primary,
                    created_by=actor_id,
                )
                self.session.add(asset)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                record_audit(
                    self.session,
                    brand_id=brand_id,
                    actor_id=actor_id,
                    action="product_media.created",
                    resource_type="product_media_asset",
                    resource_id=asset.id,
                    details={"product_item_id": str(product_item_id)},
                )
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return asset

    async def make_primary(
        self, *, brand_id: uuid.UUID, asset_id: uuid.UUID, actor_id: uuid.UUID
    ) -> ProductMediaAsset:
        async with self.session.begin():
            asset = await self.session.scalar(
                select(ProductMediaAsset)
                .where(
                    ProductMediaAsset.id == asset_id,
                    ProductMediaAsset.brand_id == brand_id,
                )
                .with_for_update()
            )
            if asset is None:
                raise NotFoundError("product media not found")
            await self.session.execute(
                update(ProductMediaAsset)
                .where(
                    ProductMediaAsset.product_item_id == asset.product_item_id,
                    ProductMediaAsset.brand_id == brand_id,
                )
                .values(is_primary=False)
            )
            asset.is_primary = True
            record_audit(
                self.session,
                brand_id=brand_id,
                actor_id=actor_id,
                action="product_media.primary_changed",
                resource_type="product_media_asset",
                resource_id=asset.id,
                details={},
            )
        return asset

    def resolve(self, storage_key: str) -> Path:
        path = (self.root / storage_key).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            raise NotFoundError("product media file not found")
        return path
