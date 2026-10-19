"""Fictional fixtures seeded through the original domain services."""

import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from smart_growth_agent.db.models import Brand
from smart_growth_agent.db.session import SessionFactory
from smart_growth_agent.domain.enums import RegistryType, Role, VerificationStatus
from smart_growth_agent.schemas.registry import EvidenceDocumentCreate, RegistryItemCreate
from smart_growth_agent.schemas.runs import CampaignBriefCreate
from smart_growth_agent.services.auth import AuthService
from smart_growth_agent.services.prompt_seed import (
    load_prompt_seed_file,
    load_single_seed_file,
    seed_prompts,
    seed_registry_entries,
    seed_scoring_rubric,
)
from smart_growth_agent.services.registry import RegistryService
from smart_growth_agent.services.runs import RunService

ROOT = Path(__file__).resolve().parents[1]
STATE = Path(os.environ.get("SMART_GROWTH_DEMO_STATE_PATH", ROOT / ".runtime/demo-state.json"))


async def seed_demo(password, *, session_factory=SessionFactory, state_path=STATE):
    async with session_factory() as session:
        existing = await session.scalar(select(Brand).where(Brand.slug == "paper-orbit-fictional"))
    if existing is not None:
        if not state_path.exists():
            raise RuntimeError("existing_demo_requires_state_manifest")
        return json.loads(state_path.read_text())
    async with session_factory() as session:
        brand, user = await AuthService(session).bootstrap_admin(
            brand_name="纸间星球（虚构演示）",
            brand_slug="paper-orbit-fictional",
            email="admin@paper-orbit.example",
            display_name="演示管理员",
            password=password,
        )
        brand_id, actor_id = brand.id, user.id
    users = {"admin": str(actor_id)}
    for role in (Role.EDITOR, Role.REVIEWER):
        async with session_factory() as session:
            member, _ = await AuthService(session).create_member(
                brand_id=brand_id,
                email=f"{role.value}@paper-orbit.example",
                display_name="演示" + role.value,
                password=secrets.token_urlsafe(24),
                role=role,
                actor_id=actor_id,
            )
            users[role.value] = str(member.id)

    async def item(kind, key, payload):
        async with session_factory() as session:
            service = RegistryService(session)
            obj, revision = await service.create_item(
                brand_id=brand_id,
                registry_type=kind,
                actor_id=actor_id,
                data=RegistryItemCreate(
                    stable_key=key,
                    payload=payload,
                    source_uri="synthetic://paper-orbit/fictional-fixture",
                    verification_status=VerificationStatus.VERIFIED,
                ),
            )
            await service.activate_revision(
                brand_id=brand_id, revision_id=revision.id, actor_id=actor_id
            )
            return obj.id, revision.id

    await item(
        RegistryType.BRAND_PROFILE,
        "paper-orbit-brand",
        {
            "name": "纸间星球（虚构）",
            "positioning": "用于软件验证的虚构文具品牌",
            "brand_story": "所有产品资料、证据与指标均为演示编写，不对应真实公司。",
            "voice": ["清晰", "克制", "友好"],
            "forbidden_tones": ["效果保证", "伪造体验"],
        },
    )
    product_id, _ = await item(
        RegistryType.PRODUCT,
        "orbit-note-01",
        {
            "name": "轨迹点阵笔记本",
            "sku": "NOTE01",
            "product_type": "stationery",
            "description": "虚构的纸质笔记本，用于记录灵感与待办。",
            "features": ["采用 A5 尺寸", "内页为点阵布局", "封面有雾蓝与砂白两种颜色"],
            "materials": ["纸质内页"],
            "non_medical_disclaimer": "虚构文具示例，不涉及健康或医疗用途",
        },
    )
    async with session_factory() as session:
        service = RegistryService(session)
        evidence = await service.create_evidence(
            brand_id=brand_id,
            actor_id=actor_id,
            data=EvidenceDocumentCreate(
                title="虚构产品规格卡（仅软件演示）",
                document_type="fictional_specification",
                source_uri="synthetic://paper-orbit/spec",
                content="虚构产品：轨迹点阵笔记本。采用 A5 尺寸；内页为点阵布局；"
                "封面有雾蓝与砂白两种颜色。不是现实产品认证。",
            ),
        )
        await service.verify_evidence(brand_id=brand_id, document_id=evidence.id, actor_id=actor_id)
        evidence_id = evidence.id
    await item(
        RegistryType.PRODUCT_CLAIM,
        "orbit-dot-layout",
        {
            "statement": "内页为点阵布局",
            "allowed_expressions": ["内页为点阵布局"],
            "forbidden_expressions": ["保证提高效率"],
            "risk_level": "low",
            "product_item_ids": [str(product_id)],
            "evidence_document_ids": [str(evidence_id)],
        },
    )
    audience_id, _ = await item(
        RegistryType.AUDIENCE,
        "orbit-audience",
        {
            "name": "虚构记录爱好者",
            "description": "喜欢纸笔记录的演示人群",
            "scenarios": ["整理待办", "记录灵感"],
            "needs": ["清晰记录"],
            "objections": ["不需要效果承诺"],
        },
    )
    await item(
        RegistryType.CONTENT_PATTERN,
        "orbit-scene-pattern",
        {
            "name": "场景与事实",
            "objective": "清晰介绍虚构产品",
            "structure": ["提出场景", "引用产品事实", "邀请讨论"],
            "cautions": ["不冒充使用体验"],
        },
    )
    await item(
        RegistryType.PLATFORM_MARKETING_PROGRAM,
        "orbit-demo-program",
        {
            "platform": "xhs",
            "name": "虚构内容测试方案",
            "program_type": "content_boost",
            "objectives": ["content_validation"],
            "description": "仅用于软件演示，不是真实平台计划。",
            "source_url": "https://example.com/fictional-program",
            "verified_at": datetime.now(UTC).isoformat(),
        },
    )
    await item(
        RegistryType.STRATEGY_INSIGHT,
        "orbit-demo-insight",
        {
            "observation": "尚无真实发布数据",
            "hypothesis": "不同记录场景可能适合不同表达",
            "recommended_actions": ["先做小规模内容审核验证"],
            "confidence": 0.2,
            "attribution_scope": "correlative",
        },
    )
    params = {"session_factory": session_factory, "brand_id": brand_id, "actor_id": actor_id}
    await seed_prompts(
        **params,
        entries=load_prompt_seed_file(ROOT / "smart_growth_agent/prompts/phase2_templates.json"),
        source_uri="synthetic://paper-orbit/prompts-v1",
    )
    await seed_scoring_rubric(
        **params,
        entry=load_single_seed_file(ROOT / "smart_growth_agent/knowledge/brand/phase4_rubric.json"),
        source_uri="synthetic://paper-orbit/demo-rubric-v1",
    )
    await seed_registry_entries(
        **params,
        entries=load_prompt_seed_file(
            ROOT / "smart_growth_agent/knowledge/platform/xhs_demo_rules.json"
        ),
        source_uri="synthetic://paper-orbit/demo-rules-v1",
        registry_type=RegistryType.PLATFORM_RULE,
    )
    async with session_factory() as session:
        brief = await RunService(session).create_brief(
            brand_id=brand_id,
            actor_id=actor_id,
            data=CampaignBriefCreate(
                name="虚构笔记本 · 内容审核演示",
                objective="向记录爱好者介绍虚构笔记本的纸笔记录场景，不承诺效率或健康效果。",
                product_item_ids=[product_id],
                audience_item_ids=[audience_id],
                constraints={
                    "body_length": 150,
                    "marketing_support_policy": "organic_only",
                    "tone": ["清晰", "克制"],
                    "scenario": "纸笔记录灵感",
                    "forbidden_points": ["真实使用体验", "产品效果保证", "未提供的参数"],
                },
            ),
        )
    result = {
        "brand_id": str(brand_id),
        "users": users,
        "brief_id": str(brief.id),
        "product_id": str(product_id),
        "fictional": True,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result
