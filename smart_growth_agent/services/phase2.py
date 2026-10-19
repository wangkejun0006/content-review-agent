from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from smart_growth_agent.db.models import (
    CampaignBrief,
    ContentCandidate,
    ContentClaimUsage,
    ContentVersion,
    GrowthRun,
    LLMCallLog,
    ProductMediaAsset,
    RegistryItem,
    RegistryRevision,
    RunContextPackage,
    RunRegistrySnapshot,
    StrategyPlan,
)
from smart_growth_agent.domain.enums import ContextType, RegistryType, VerificationStatus
from smart_growth_agent.llm.gateway import LLMGateway
from smart_growth_agent.llm.types import ChatMessage, LLMRequest, LLMResult
from smart_growth_agent.research.gateway import ResearchGateway, ResearchRequest
from smart_growth_agent.schemas.phase2 import (
    ContentCandidateRead,
    FactReference,
    PolicyContextOutput,
    PolicyRuleReference,
    ProductContextOutput,
    StrategyOutput,
    WriterOutput,
)
from smart_growth_agent.services.knowledge import KnowledgeService

PROMPT_PRODUCT_CONTEXT = "xhs_product_context"
PROMPT_STRATEGY = "xhs_strategy"
PROMPT_WRITER = "xhs_writer"


def canonical_checksum(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def generation_key(*parts: object) -> str:
    return hashlib.sha256(":".join(str(part) for part in parts).encode()).hexdigest()


class Phase2Service:
    _sqlite_write_locks: dict[int, tuple[asyncio.AbstractEventLoop, asyncio.Lock]] = {}

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm_gateway: LLMGateway,
        research_gateway: ResearchGateway,
    ) -> None:
        self.session_factory = session_factory
        self.llm_gateway = llm_gateway
        self.research_gateway = research_gateway

    async def check_knowledge_freshness(
        self, *, brand_id: uuid.UUID, run_id: uuid.UUID
    ) -> tuple[bool, list[dict[str, Any]]]:
        async with self.session_factory() as session:
            issues = await KnowledgeService(session).evaluate_run_freshness(
                brand_id=brand_id, run_id=run_id
            )
        serialized = [issue.model_dump(mode="json") for issue in issues]
        return False, serialized

    async def build_product_context(
        self, *, brand_id: uuid.UUID, run_id: uuid.UUID
    ) -> uuid.UUID:
        _run, brief, rows = await self._load_run_inputs(brand_id, run_id)
        existing = await self._get_context(run_id, ContextType.PRODUCT)
        if existing is not None:
            return existing.id
        prompt_item, prompt = self._require_prompt(rows, PROMPT_PRODUCT_CONTEXT)
        evidence_packet = {
            "brief": {
                "objective": brief.objective,
                "constraints": brief.constraints,
            },
            "governance": {
                "allowed_claim_revision_ids": [
                    str(revision.id)
                    for item, revision, _purpose in rows
                    if item.registry_type == RegistryType.PRODUCT_CLAIM
                ],
                "empty_claim_policy": (
                    "allowed_claims 必须为空数组；把缺少已激活 Product Claim 和证据写入 "
                    "missing_information，不得自行构造 Claim ID"
                ),
            },
            "registry": [
                {
                    "item_id": str(item.id),
                    "revision_id": str(revision.id),
                    "registry_type": item.registry_type.value,
                    "stable_key": item.stable_key,
                    "verification_status": revision.verification_status.value,
                    "payload": revision.payload,
                }
                for item, revision, _purpose in rows
                if item.registry_type != RegistryType.PROMPT_TEMPLATE
            ],
            "deterministic_product_facts": [
                {
                    "revision_id": str(revision.id),
                    "field_path": field_path,
                    "statement": statement,
                    "verification_status": revision.verification_status.value,
                }
                for item, revision, _purpose in rows
                if item.registry_type == RegistryType.PRODUCT
                for field_path, statement in self._product_fact_statements(revision.payload)
            ],
        }
        input_checksum = canonical_checksum(evidence_packet)
        key = generation_key(run_id, "product_context", prompt.id, input_checksum)
        result = await self.llm_gateway.generate(
            LLMRequest(
                brand_id=brand_id,
                run_id=run_id,
                purpose="xhs_product_context",
                prompt_revision_id=prompt.id,
                temperature=0.2,
                messages=[
                    ChatMessage(role="system", content=prompt.payload["template"]),
                    ChatMessage(
                        role="user",
                        content=json.dumps(evidence_packet, ensure_ascii=False, sort_keys=True),
                    ),
                ],
            ),
            ProductContextOutput,
        )
        context_output = self._apply_product_context_governance(result.value, rows)
        self._validate_product_context(context_output, rows)
        return await self._persist_context(
            brand_id=brand_id,
            run_id=run_id,
            context_type=ContextType.PRODUCT,
            payload=context_output.model_dump(mode="json"),
            input_checksum=input_checksum,
            generation_key_value=key,
            prompt_revision_id=prompt.id,
            llm_result=result,
        )

    async def build_policy_context(
        self, *, brand_id: uuid.UUID, run_id: uuid.UUID
    ) -> uuid.UUID:
        existing = await self._get_context(run_id, ContextType.POLICY)
        if existing is not None:
            return existing.id
        _run, _brief, rows = await self._load_run_inputs(brand_id, run_id)
        async with self.session_factory() as session:
            issues = await KnowledgeService(session).evaluate_run_freshness(
                brand_id=brand_id, run_id=run_id
            )
        stale_ids = {issue.revision_id for issue in issues}
        rules = [
            PolicyRuleReference(
                revision_id=revision.id,
                stable_key=item.stable_key,
                category=revision.payload["category"],
                rule_text=revision.payload["rule_text"],
                severity=revision.payload["severity"],
                source_url=str(revision.payload["source_url"]),
                stale=revision.id in stale_ids,
            )
            for item, revision, _purpose in rows
            if item.registry_type == RegistryType.PLATFORM_RULE
        ]
        output = PolicyContextOutput(
            rules=rules,
            freshness_warnings=[issue.message for issue in issues],
        )
        payload = output.model_dump(mode="json")
        checksum = canonical_checksum(payload)
        return await self._persist_context(
            brand_id=brand_id,
            run_id=run_id,
            context_type=ContextType.POLICY,
            payload=payload,
            input_checksum=checksum,
            generation_key_value=generation_key(run_id, "policy_context", checksum),
        )

    async def build_trend_context(
        self, *, brand_id: uuid.UUID, run_id: uuid.UUID
    ) -> uuid.UUID:
        existing = await self._get_context(run_id, ContextType.TREND)
        if existing is not None:
            return existing.id
        _run, brief, rows = await self._load_run_inputs(brand_id, run_id)
        products = [
            revision.payload["name"]
            for item, revision, _purpose in rows
            if item.registry_type == RegistryType.PRODUCT
        ]
        audiences = [
            revision.payload["name"]
            for item, revision, _purpose in rows
            if item.registry_type == RegistryType.AUDIENCE
        ]
        request = ResearchRequest(
            brand_id=brand_id,
            run_id=run_id,
            product_keywords=products,
            audience_keywords=audiences,
            platforms=["xiaohongshu", "douyin", "weibo", "instagram"],
            time_window_days=7,
        )
        output = await self.research_gateway.research(request)
        payload = output.model_dump(mode="json")
        checksum = canonical_checksum(
            {"request": request.model_dump(mode="json"), "brief": brief.objective}
        )
        return await self._persist_context(
            brand_id=brand_id,
            run_id=run_id,
            context_type=ContextType.TREND,
            payload=payload,
            input_checksum=checksum,
            generation_key_value=generation_key(run_id, "trend_context", checksum),
        )

    async def build_strategy(self, *, brand_id: uuid.UUID, run_id: uuid.UUID) -> uuid.UUID:
        async with self.session_factory() as session:
            existing = await session.scalar(
                select(StrategyPlan).where(StrategyPlan.run_id == run_id)
            )
            if existing is not None:
                return existing.id
        _run, brief, rows = await self._load_run_inputs(brand_id, run_id)
        _prompt_item, prompt = self._require_prompt(rows, PROMPT_STRATEGY)
        contexts = await self._load_all_contexts(run_id)
        input_payload = {
            "brief": {
                "objective": brief.objective,
                "constraints": brief.constraints,
            },
            "product_context": contexts[ContextType.PRODUCT].payload,
            "policy_context": contexts[ContextType.POLICY].payload,
            "trend_context": contexts[ContextType.TREND].payload,
            "marketing_programs": [
                {
                    "revision_id": str(revision.id),
                    "stable_key": item.stable_key,
                    "payload": revision.payload,
                }
                for item, revision, _purpose in rows
                if item.registry_type == RegistryType.PLATFORM_MARKETING_PROGRAM
            ],
        }
        checksum = canonical_checksum(input_payload)
        key = generation_key(run_id, "strategy", prompt.id, checksum)
        result = await self.llm_gateway.generate(
            LLMRequest(
                brand_id=brand_id,
                run_id=run_id,
                purpose="xhs_strategy",
                prompt_revision_id=prompt.id,
                temperature=0.3,
                messages=[
                    ChatMessage(role="system", content=prompt.payload["template"]),
                    ChatMessage(
                        role="user",
                        content=json.dumps(input_payload, ensure_ascii=False, sort_keys=True),
                    ),
                ],
            ),
            StrategyOutput,
        )
        allowed_claims = {
            uuid.UUID(value["claim_revision_id"])
            for value in contexts[ContextType.PRODUCT].payload.get("allowed_claims", [])
        }
        for route in result.value.creative_routes:
            if not set(route.allowed_claim_revision_ids) <= allowed_claims:
                raise ValueError("strategy referenced a claim outside product context")
        available_program_ids = {
            revision.id
            for item, revision, _purpose in rows
            if item.registry_type == RegistryType.PLATFORM_MARKETING_PROGRAM
        }
        recommendation = result.value.marketing_support
        if recommendation.policy != brief.constraints.get(
            "marketing_support_policy", "evaluate"
        ):
            raise ValueError("strategy changed the Brief marketing support policy")
        if not set(recommendation.program_revision_ids) <= available_program_ids:
            raise ValueError("strategy referenced a marketing program outside run snapshot")
        if recommendation.policy == "organic_only" and (
            recommendation.recommended or recommendation.program_revision_ids
        ):
            raise ValueError("organic-only Brief cannot recommend a paid marketing program")
        async with self.session_factory() as session, session.begin():
            plan = StrategyPlan(
                brand_id=brand_id,
                run_id=run_id,
                payload=result.value.model_dump(mode="json"),
                prompt_revision_id=prompt.id,
                input_checksum=checksum,
                generation_key=key,
            )
            session.add(plan)
            await session.flush()
            self._add_llm_log(session, brand_id, run_id, prompt.id, "xhs_strategy", result)
            return plan.id

    async def write_candidate(
        self, *, brand_id: uuid.UUID, run_id: uuid.UUID, route_key: str
    ) -> uuid.UUID:
        async with self.session_factory() as session:
            existing = await session.scalar(
                select(ContentCandidate).where(
                    ContentCandidate.run_id == run_id,
                    ContentCandidate.route_key == route_key,
                )
            )
            if existing is not None:
                return existing.id
        run, brief, rows = await self._load_run_inputs(brand_id, run_id)
        _prompt_item, prompt = self._require_prompt(rows, PROMPT_WRITER)
        contexts = await self._load_all_contexts(run_id)
        async with self.session_factory() as session:
            plan = await session.scalar(select(StrategyPlan).where(StrategyPlan.run_id == run_id))
            if plan is None:
                raise RuntimeError("strategy plan is missing")
        strategy = StrategyOutput.model_validate(plan.payload)
        route = next(
            (item for item in strategy.creative_routes if item.route_key == route_key), None
        )
        if route is None:
            raise ValueError("creative route is missing from strategy")
        selected_product_ids = {uuid.UUID(value) for value in brief.product_item_ids}
        async with self.session_factory() as session:
            product_media = list(
                await session.scalars(
                    select(ProductMediaAsset).where(
                        ProductMediaAsset.brand_id == brand_id,
                        ProductMediaAsset.product_item_id.in_(selected_product_ids),
                    )
                )
            )
        input_payload = {
            "brief": {
                "objective": brief.objective,
                "constraints": brief.constraints,
            },
            "product_context": contexts[ContextType.PRODUCT].payload,
            "policy_context": contexts[ContextType.POLICY].payload,
            "trend_context": contexts[ContextType.TREND].payload,
            "creative_route": route.model_dump(mode="json"),
            "product_media": [
                {
                    "id": str(asset.id),
                    "product_item_id": str(asset.product_item_id),
                    "file_name": asset.file_name,
                    "alt_text": asset.alt_text,
                    "width": asset.width,
                    "height": asset.height,
                    "is_primary": asset.is_primary,
                }
                for asset in product_media
            ],
        }
        checksum = canonical_checksum(input_payload)
        key = generation_key(run_id, "writer", route_key, prompt.id, checksum)
        result = await self.llm_gateway.generate(
            LLMRequest(
                brand_id=brand_id,
                run_id=run_id,
                purpose="xhs_writer",
                prompt_revision_id=prompt.id,
                temperature=0.6,
                messages=[
                    ChatMessage(role="system", content=prompt.payload["template"]),
                    ChatMessage(
                        role="user",
                        content=json.dumps(input_payload, ensure_ascii=False, sort_keys=True),
                    ),
                ],
            ),
            WriterOutput,
        )
        self._validate_writer_output(
            result.value,
            route,
            contexts[ContextType.PRODUCT].payload,
            rows,
            {asset.id for asset in product_media},
        )
        async with self._candidate_write_guard():
            async with self.session_factory() as session, session.begin():
                candidate = ContentCandidate(
                    brand_id=brand_id,
                    run_id=run_id,
                    route_key=route.route_key,
                    angle_key=route.angle_key,
                    current_version=1,
                )
                session.add(candidate)
                await session.flush()
                version = ContentVersion(
                    brand_id=brand_id,
                    candidate_id=candidate.id,
                    version=1,
                    payload=result.value.model_dump(mode="json"),
                    prompt_revision_id=prompt.id,
                    input_checksum=checksum,
                    generation_key=key,
                )
                session.add(version)
                await session.flush()
                for claim_id in result.value.cited_claim_revision_ids:
                    session.add(
                        ContentClaimUsage(
                            brand_id=brand_id,
                            content_version_id=version.id,
                            claim_revision_id=claim_id,
                            usage_type="explicit",
                            content_excerpt="",
                        )
                    )
                for claim_id in result.value.media_plan.claim_revision_ids:
                    session.add(
                        ContentClaimUsage(
                            brand_id=brand_id,
                            content_version_id=version.id,
                            claim_revision_id=claim_id,
                            usage_type="visual",
                            content_excerpt=result.value.media_plan.preferred_generation_prompt[
                                :500
                            ],
                        )
                    )
                self._add_llm_log(
                    session, brand_id, run_id, prompt.id, "xhs_writer", result
                )
                return candidate.id

    async def list_candidates(
        self, *, brand_id: uuid.UUID, run_id: uuid.UUID
    ) -> list[ContentCandidateRead]:
        async with self.session_factory() as session:
            rows = list(
                (
                    await session.execute(
                        select(ContentCandidate, ContentVersion)
                        .join(
                            ContentVersion,
                            (ContentVersion.candidate_id == ContentCandidate.id)
                            & (ContentVersion.version == ContentCandidate.current_version),
                        )
                        .where(
                            ContentCandidate.brand_id == brand_id,
                            ContentCandidate.run_id == run_id,
                        )
                    )
                ).all()
            )
            plan = await session.scalar(
                select(StrategyPlan).where(StrategyPlan.run_id == run_id)
            )
        route_order = (
            {
                route.route_key: index
                for index, route in enumerate(
                    StrategyOutput.model_validate(plan.payload).creative_routes
                )
            }
            if plan is not None
            else {}
        )
        rows.sort(key=lambda row: route_order.get(row[0].route_key, 999))
        return [
            ContentCandidateRead(
                id=candidate.id,
                route_key=candidate.route_key,
                angle_key=candidate.angle_key,
                current_version=candidate.current_version,
                content_version_id=version.id,
                payload=WriterOutput.model_validate(version.payload),
            )
            for candidate, version in rows
        ]

    async def _load_run_inputs(
        self, brand_id: uuid.UUID, run_id: uuid.UUID
    ) -> tuple[GrowthRun, CampaignBrief, list[tuple[RegistryItem, RegistryRevision, str]]]:
        async with self.session_factory() as session:
            run = await session.scalar(
                select(GrowthRun).where(GrowthRun.id == run_id, GrowthRun.brand_id == brand_id)
            )
            if run is None:
                raise RuntimeError("growth run not found")
            brief = await session.get(CampaignBrief, run.brief_id)
            if brief is None:
                raise RuntimeError("campaign brief not found")
            rows = list(
                (
                    await session.execute(
                        select(RegistryItem, RegistryRevision, RunRegistrySnapshot.purpose)
                        .join(
                            RunRegistrySnapshot,
                            RunRegistrySnapshot.item_id == RegistryItem.id,
                        )
                        .join(
                            RegistryRevision,
                            RegistryRevision.id == RunRegistrySnapshot.revision_id,
                        )
                        .where(
                            RunRegistrySnapshot.run_id == run_id,
                            RunRegistrySnapshot.brand_id == brand_id,
                        )
                    )
                ).all()
            )
        return run, brief, rows

    async def _get_context(
        self, run_id: uuid.UUID, context_type: ContextType
    ) -> RunContextPackage | None:
        async with self.session_factory() as session:
            return await session.scalar(
                select(RunContextPackage).where(
                    RunContextPackage.run_id == run_id,
                    RunContextPackage.context_type == context_type,
                )
            )

    async def _load_all_contexts(
        self, run_id: uuid.UUID
    ) -> dict[ContextType, RunContextPackage]:
        async with self.session_factory() as session:
            packages = list(
                await session.scalars(
                    select(RunContextPackage).where(RunContextPackage.run_id == run_id)
                )
            )
        result = {package.context_type: package for package in packages}
        missing = set(ContextType) - set(result)
        if missing:
            missing_names = sorted(item.value for item in missing)
            raise RuntimeError(f"context packages are missing: {missing_names}")
        return result

    async def _persist_context(
        self,
        *,
        brand_id: uuid.UUID,
        run_id: uuid.UUID,
        context_type: ContextType,
        payload: dict[str, Any],
        input_checksum: str,
        generation_key_value: str,
        prompt_revision_id: uuid.UUID | None = None,
        llm_result: LLMResult | None = None,
    ) -> uuid.UUID:
        async with self.session_factory() as session, session.begin():
            package = RunContextPackage(
                brand_id=brand_id,
                run_id=run_id,
                context_type=context_type,
                payload=payload,
                input_checksum=input_checksum,
                generation_key=generation_key_value,
                prompt_revision_id=prompt_revision_id,
            )
            session.add(package)
            await session.flush()
            if llm_result is not None and prompt_revision_id is not None:
                self._add_llm_log(
                    session,
                    brand_id,
                    run_id,
                    prompt_revision_id,
                    context_type.value,
                    llm_result,
                )
            return package.id

    @staticmethod
    def _require_prompt(
        rows: list[tuple[RegistryItem, RegistryRevision, str]], stable_key: str
    ) -> tuple[RegistryItem, RegistryRevision]:
        for item, revision, _purpose in rows:
            if item.registry_type == RegistryType.PROMPT_TEMPLATE and item.stable_key == stable_key:
                return item, revision
        raise RuntimeError(f"required prompt revision is missing from run snapshot: {stable_key}")

    @staticmethod
    def _apply_product_context_governance(
        output: ProductContextOutput,
        rows: list[tuple[RegistryItem, RegistryRevision, str]],
    ) -> ProductContextOutput:
        """Deterministically enforce the no-Claim path after an LLM response.

        An empty Claim Registry is an explicit business state, not a reason to let the
        model invent identifiers. Invalid references remain blocking when real Claims
        exist, while the zero-Claim path is safely reduced to provisional product facts.
        """
        has_product_claims = any(
            item.registry_type == RegistryType.PRODUCT_CLAIM
            for item, _revision, _purpose in rows
        )
        fact_source_types = {
            RegistryType.PRODUCT,
            RegistryType.BRAND_PROFILE,
            RegistryType.AUDIENCE,
        }
        fact_revisions = {
            revision.id: (item, revision)
            for item, revision, _purpose in rows
            if item.registry_type in fact_source_types
        }
        relevant_facts = []
        provisional_facts = []
        seen_facts: set[tuple[uuid.UUID, str]] = set()
        dropped_facts = 0
        for fact in [*output.relevant_facts, *output.provisional_facts]:
            source = fact_revisions.get(fact.revision_id)
            if source is None or fact.statement not in Phase2Service._string_values(
                source[1].payload
            ):
                dropped_facts += 1
                continue
            marker = (fact.revision_id, fact.statement)
            if marker in seen_facts:
                continue
            seen_facts.add(marker)
            target = (
                provisional_facts
                if source[1].verification_status == VerificationStatus.PROVISIONAL
                else relevant_facts
            )
            target.append(fact)

        # A real model may paraphrase or omit facts even when asked to quote them.
        # Never accept a paraphrase as a fact.  The exact product catalog is merged
        # back deterministically so Writer/Compliance always receive the product
        # name, description, features, materials and disclaimer from the frozen
        # Registry Revision rather than an LLM reconstruction.
        for item, revision, _purpose in rows:
            if item.registry_type != RegistryType.PRODUCT:
                continue
            for _field_path, statement in Phase2Service._product_fact_statements(
                revision.payload
            ):
                marker = (revision.id, statement)
                if marker in seen_facts:
                    continue
                seen_facts.add(marker)
                target = (
                    provisional_facts
                    if revision.verification_status == VerificationStatus.PROVISIONAL
                    else relevant_facts
                )
                target.append(FactReference(revision_id=revision.id, statement=statement))

        missing_information = list(output.missing_information)
        allowed_claims = output.allowed_claims
        if dropped_facts:
            missing_information.append(
                f"模型返回的 {dropped_facts} 条事实未能逐字映射到 Registry 快照，"
                "已丢弃；内容仅可使用保留下来的原文事实。"
            )
        if not has_product_claims:
            allowed_claims = []
            missing_information.append(
                "当前产品没有已激活的 Product Claim 或可验证证据；"
                "仍可生成基于产品资料的内容，但不得补充准确率、健康功效或其他未证实结论。"
            )
        product_names = [
            revision.payload.get("name")
            for item, revision, _purpose in rows
            if item.registry_type == RegistryType.PRODUCT
            and isinstance(revision.payload.get("name"), str)
        ]
        governed_summary = (
            f"已根据 {'、'.join(product_names) or '所选产品'} 的 Registry 快照整理上下文；"
            "所有可使用事实以 relevant_facts 和 provisional_facts 为准，"
            "缺失与限制见 missing_information。"
        )
        return output.model_copy(
            update={
                "summary": governed_summary,
                "relevant_facts": relevant_facts,
                "provisional_facts": provisional_facts,
                "allowed_claims": allowed_claims,
                "missing_information": list(dict.fromkeys(missing_information)),
            }
        )

    @staticmethod
    def _validate_product_context(
        output: ProductContextOutput,
        rows: list[tuple[RegistryItem, RegistryRevision, str]],
    ) -> None:
        revision_ids = {revision.id for _item, revision, _purpose in rows}
        revisions_by_id = {revision.id: revision for _item, revision, _purpose in rows}
        claim_ids = {
            revision.id
            for item, revision, _purpose in rows
            if item.registry_type == RegistryType.PRODUCT_CLAIM
        }
        referenced = {
            item.revision_id for item in [*output.relevant_facts, *output.provisional_facts]
        }
        if not referenced <= revision_ids:
            raise ValueError("product context referenced revisions outside run snapshot")
        if not {item.claim_revision_id for item in output.allowed_claims} <= claim_ids:
            raise ValueError("product context referenced claims outside run snapshot")
        for fact in [*output.relevant_facts, *output.provisional_facts]:
            source_values = Phase2Service._string_values(
                revisions_by_id[fact.revision_id].payload
            )
            if fact.statement not in source_values:
                raise ValueError("product context fact is not present in its cited revision")
        for claim in output.allowed_claims:
            claim_payload = revisions_by_id[claim.claim_revision_id].payload
            if claim.statement != claim_payload["statement"]:
                raise ValueError("product context changed the cited claim statement")
            if claim.allowed_expression not in claim_payload["allowed_expressions"]:
                raise ValueError("product context used an expression not allowed by the claim")

    @staticmethod
    def _string_values(value: Any) -> set[str]:
        if isinstance(value, str):
            return {value}
        if isinstance(value, dict):
            result: set[str] = set()
            for child in value.values():
                result.update(Phase2Service._string_values(child))
            return result
        if isinstance(value, list):
            result = set()
            for child in value:
                result.update(Phase2Service._string_values(child))
            return result
        return set()

    @staticmethod
    def _product_fact_statements(payload: dict[str, Any]) -> list[tuple[str, str]]:
        """Return ordered, operator-authored product facts with stable field paths."""

        values: list[tuple[str, str]] = []
        for field in ("name", "sku", "description", "non_medical_disclaimer"):
            value = payload.get(field)
            if isinstance(value, str) and value.strip():
                values.append((field, value.strip()))
        for field in ("features", "materials"):
            raw_values = payload.get(field)
            if not isinstance(raw_values, list):
                continue
            for index, value in enumerate(raw_values):
                if isinstance(value, str) and value.strip():
                    values.append((f"{field}[{index}]", value.strip()))
        return list(dict.fromkeys(values))

    @staticmethod
    def _validate_writer_output(
        output: WriterOutput,
        route: Any,
        product_context: dict[str, Any],
        rows: list[tuple[RegistryItem, RegistryRevision, str]],
        product_media_ids: set[uuid.UUID] | None = None,
    ) -> None:
        if output.route_key != route.route_key or output.angle_key != route.angle_key:
            raise ValueError("writer output route identity does not match strategy")
        allowed_claims = {
            uuid.UUID(item["claim_revision_id"])
            for item in product_context.get("allowed_claims", [])
        }
        if not set(output.cited_claim_revision_ids) <= allowed_claims:
            raise ValueError("writer cited a claim outside product context")
        if not set(output.media_plan.claim_revision_ids) <= allowed_claims:
            raise ValueError("media plan cited a claim outside product context")
        if not set(output.media_plan.product_media_ids) <= (product_media_ids or set()):
            raise ValueError("media plan referenced media outside selected Brief products")
        snapshot_ids = {revision.id for _item, revision, _purpose in rows}
        if not set(output.source_revision_ids) <= snapshot_ids:
            raise ValueError("writer cited a revision outside run snapshot")

    @staticmethod
    def _add_llm_log(
        session: AsyncSession,
        brand_id: uuid.UUID,
        run_id: uuid.UUID,
        prompt_revision_id: uuid.UUID,
        purpose: str,
        result: LLMResult,
    ) -> None:
        if result.telemetry_logged:
            return
        session.add(
            LLMCallLog(
                brand_id=brand_id,
                run_id=run_id,
                provider=result.provider,
                model=result.model,
                purpose=purpose,
                prompt_revision_id=prompt_revision_id,
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                latency_ms=result.latency_ms,
                provider_request_id=result.provider_request_id,
            )
        )

    @asynccontextmanager
    async def _candidate_write_guard(self) -> AsyncIterator[None]:
        bind = self.session_factory.kw.get("bind")
        if bind is not None and bind.dialect.name == "sqlite":
            loop = asyncio.get_running_loop()
            engine_key = id(bind)
            entry = self._sqlite_write_locks.get(engine_key)
            if entry is None or entry[0] is not loop:
                entry = (loop, asyncio.Lock())
                self._sqlite_write_locks[engine_key] = entry
            async with entry[1]:
                yield
            return
        yield
