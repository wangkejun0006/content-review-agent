from __future__ import annotations

import io

import pytest
from PIL import Image
from pydantic import SecretStr

from smart_growth_agent.config import Settings
from smart_growth_agent.db.models import Brand
from smart_growth_agent.domain.enums import RegistryType
from smart_growth_agent.domain.errors import ValidationError
from smart_growth_agent.schemas.registry import RegistryItemCreate
from smart_growth_agent.services.media import ProductMediaService
from smart_growth_agent.services.registry import RegistryService


def _png(color: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_product_media_validates_image_and_manages_primary(
    session_factory, tmp_path
) -> None:
    settings = Settings(
        media_storage_path=tmp_path / "media",
        credential_encryption_key=SecretStr("test-credential-key"),
    )
    async with session_factory() as session, session.begin():
        brand = Brand(name="Media Brand", slug="media-brand")
        session.add(brand)
        await session.flush()
        brand_id = brand.id
    async with session_factory() as session:
        product, _revision = await RegistryService(session).create_item(
            brand_id=brand_id,
            registry_type=RegistryType.PRODUCT,
            actor_id=brand_id,
            data=RegistryItemCreate(
                stable_key="media-product",
                payload={
                    "name": "Media Product",
                    "product_type": "stationery",
                    "description": "Test product",
                    "features": ["Test feature"],
                },
            ),
        )
        service = ProductMediaService(session, settings)
        first = await service.create(
            brand_id=brand_id,
            product_item_id=product.id,
            file_name="front.png",
            content=_png("blue"),
            alt_text="正面图",
            is_primary=False,
            actor_id=brand_id,
        )
        assert first.is_primary is True
        assert service.resolve(first.storage_key).is_file()
        second = await service.create(
            brand_id=brand_id,
            product_item_id=product.id,
            file_name="side.png",
            content=_png("red"),
            alt_text="侧面图",
            is_primary=True,
            actor_id=brand_id,
        )
        assert second.is_primary is True
        await session.refresh(first)
        assert first.is_primary is False


def test_product_media_rejects_non_image() -> None:
    with pytest.raises(ValidationError, match="不是有效"):
        ProductMediaService.inspect_image(b"not-an-image")
