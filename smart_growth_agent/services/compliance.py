from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pydantic_core import to_jsonable_python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from smart_growth_agent.db.models import (
    ComplianceFinding,
    ComplianceReport,
    ContentCandidate,
    ContentClaimUsage,
    ContentVersion,
    GrowthRun,
    LLMCallLog,
    RegistryItem,
    RegistryRevision,
    RunContextPackage,
    RunRegistrySnapshot,
    StrategyPlan,
)
from smart_growth_agent.domain.enums import ContextType, RegistryType
from smart_growth_agent.llm.gateway import LLMGateway
from smart_growth_agent.llm.types import ChatMessage, LLMRequest
from smart_growth_agent.schemas.compliance import (
    ComplianceFindingRead,
    ComplianceReportRead,
    ComplianceSemanticOutput,
)
from smart_growth_agent.schemas.phase2 import (
    ProductContextOutput,
    StrategyOutput,
    WriterOutput,
)
from smart_growth_agent.services.phase2 import Phase2Service, canonical_checksum, generation_key

MEDICAL_TERMS = ("诊断", "治疗", "治愈", "预防疾病", "医疗级", "替代医生", "疗效")
FALSE_EXPERIENCE_PATTERNS = (
    re.compile(r"我(已经)?(戴|用了|使用)了?\s*\d+\s*(天|周|个月)"),
    re.compile(r"亲测(有效|好用|改善)"),
    re.compile(r"用了?之后.{0,20}(改善|恢复|治好|好了)"),
)
ADVERTISING_TERMS = ("闭眼入", "必须买", "全网最好", "百分百", "绝对有效")
PROMPT_COMPLIANCE = "xhs_compliance"


class ComplianceService:
    _sqlite_write_locks: dict[int, tuple[asyncio.AbstractEventLoop, asyncio.Lock]] = {}

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm_gateway: LLMGateway,
    ) -> None:
        self.session_factory = session_factory
        self.llm_gateway = llm_gateway

    async def review_content_version(
        self, *, brand_id: uuid.UUID, content_version_id: uuid.UUID
    ) -> uuid.UUID:
        async with self.session_factory() as session:
            existing = await session.scalar(
                select(ComplianceReport).where(
                    ComplianceReport.brand_id == brand_id,
                    ComplianceReport.content_version_id == content_version_id,
                )
            )
            if existing is not None:
                return existing.id
            version = await session.scalar(
                select(ContentVersion).where(
                    ContentVersion.id == content_version_id,
                    ContentVersion.brand_id == brand_id,
                )
            )
            if version is None:
                raise RuntimeError("content version not found")
            candidate = await session.get(ContentCandidate, version.candidate_id)
            if candidate is None:
                raise RuntimeError("content candidate not found")
            run = await session.get(GrowthRun, candidate.run_id)
            if run is None or run.brand_id != brand_id:
                raise RuntimeError("growth run not found")
            contexts = list(
                await session.scalars(
                    select(RunContextPackage).where(RunContextPackage.run_id == run.id)
                )
            )
            snapshot_rows = list(
                (
                    await session.execute(
                        select(RegistryItem, RegistryRevision)
                        .join(
                            RunRegistrySnapshot,
                            RunRegistrySnapshot.item_id == RegistryItem.id,
                        )
                        .join(
                            RegistryRevision,
                            RegistryRevision.id == RunRegistrySnapshot.revision_id,
                        )
                        .where(RunRegistrySnapshot.run_id == run.id)
                    )
                ).all()
            )

        prompt = self._require_prompt(snapshot_rows)
        writer = WriterOutput.model_validate(version.payload)
        product_context_row = next(
            item for item in contexts if item.context_type == ContextType.PRODUCT
        )
        product_context = ProductContextOutput.model_validate(product_context_row.payload)
        deterministic = self._deterministic_findings(
            writer=writer,
            product_context=product_context,
            snapshot_rows=snapshot_rows,
        )
        semantic_input = {
            "content": writer.model_dump(mode="json"),
            "product_context": product_context.model_dump(mode="json"),
            "policy_context": next(
                item.payload for item in contexts if item.context_type == ContextType.POLICY
            ),
            "deterministic_findings": to_jsonable_python(deterministic),
        }
        checksum = canonical_checksum(semantic_input)
        key = generation_key(content_version_id, "compliance", prompt.id, checksum)
        result = await self.llm_gateway.generate(
            LLMRequest(
                brand_id=brand_id,
                run_id=run.id,
                purpose="xhs_compliance_semantic",
                prompt_revision_id=prompt.id,
                temperature=0.1,
                messages=[
                    ChatMessage(role="system", content=prompt.payload["template"]),
                    ChatMessage(
                        role="user",
                        content=json.dumps(semantic_input, ensure_ascii=False, sort_keys=True),
                    ),
                ],
            ),
            ComplianceSemanticOutput,
        )
        self._validate_semantic_references(result.value, snapshot_rows)
        semantic_findings = [
            {
                **finding.model_dump(mode="json"),
                "source": "semantic",
                "evidence": {},
            }
            for finding in result.value.findings
        ]
        all_findings = [*deterministic, *semantic_findings]
        has_blockers = any(item["severity"] == "blocker" for item in all_findings)
        semantic_pass = not result.value.requires_revision and not any(
            item["severity"] == "blocker" for item in semantic_findings
        )
        async with self.session_factory() as session, session.begin():
            report = ComplianceReport(
                brand_id=brand_id,
                content_version_id=content_version_id,
                prompt_revision_id=prompt.id,
                deterministic_pass=not any(item["severity"] == "blocker" for item in deterministic),
                semantic_pass=semantic_pass,
                has_blockers=has_blockers,
                summary=result.value.summary,
                input_checksum=checksum,
                generation_key=key,
            )
            session.add(report)
            await session.flush()
            for item in all_findings:
                session.add(
                    ComplianceFinding(
                        brand_id=brand_id,
                        report_id=report.id,
                        category=item["category"],
                        severity=item["severity"],
                        message=item["message"],
                        evidence=item.get("evidence", {}),
                        source=item["source"],
                        evidence_excerpt=item.get("evidence_excerpt", ""),
                        suggestion=item.get("suggestion", ""),
                        rule_revision_id=item.get("rule_revision_id"),
                        claim_revision_id=item.get("claim_revision_id"),
                    )
                )
            if not result.telemetry_logged:
                session.add(
                    LLMCallLog(
                        brand_id=brand_id,
                        run_id=run.id,
                        provider=result.provider,
                        model=result.model,
                        purpose="xhs_compliance_semantic",
                        prompt_revision_id=prompt.id,
                        input_tokens=result.usage.input_tokens,
                        output_tokens=result.usage.output_tokens,
                        latency_ms=result.latency_ms,
                        provider_request_id=result.provider_request_id,
                    )
                )
            await session.flush()
            return report.id

    async def rewrite_content_version(
        self,
        *,
        brand_id: uuid.UUID,
        candidate_id: uuid.UUID,
        source_version_id: uuid.UUID,
        revision_instructions: str | None = None,
    ) -> uuid.UUID:
        async with self.session_factory() as session:
            source = await session.scalar(
                select(ContentVersion).where(
                    ContentVersion.id == source_version_id,
                    ContentVersion.candidate_id == candidate_id,
                    ContentVersion.brand_id == brand_id,
                )
            )
            candidate = await session.scalar(
                select(ContentCandidate).where(
                    ContentCandidate.id == candidate_id,
                    ContentCandidate.brand_id == brand_id,
                )
            )
            if source is None or candidate is None:
                raise RuntimeError("rewrite source content version is missing")
            run = await session.scalar(
                select(GrowthRun).where(
                    GrowthRun.id == candidate.run_id,
                    GrowthRun.brand_id == brand_id,
                )
            )
            report = await session.scalar(
                select(ComplianceReport).where(
                    ComplianceReport.content_version_id == source.id,
                    ComplianceReport.brand_id == brand_id,
                )
            )
            plan = await session.scalar(
                select(StrategyPlan).where(StrategyPlan.run_id == candidate.run_id)
            )
            contexts = list(
                await session.scalars(
                    select(RunContextPackage).where(RunContextPackage.run_id == candidate.run_id)
                )
            )
            snapshot_rows = list(
                (
                    await session.execute(
                        select(RegistryItem, RegistryRevision)
                        .join(
                            RunRegistrySnapshot,
                            RunRegistrySnapshot.item_id == RegistryItem.id,
                        )
                        .join(
                            RegistryRevision,
                            RegistryRevision.id == RunRegistrySnapshot.revision_id,
                        )
                        .where(RunRegistrySnapshot.run_id == candidate.run_id)
                    )
                ).all()
            )
            findings = (
                list(
                    await session.scalars(
                        select(ComplianceFinding)
                        .where(ComplianceFinding.report_id == report.id)
                        .order_by(ComplianceFinding.created_at)
                    )
                )
                if report is not None
                else []
            )
        if run is None or report is None or plan is None:
            raise RuntimeError("rewrite context is incomplete")
        context_by_type = {item.context_type: item for item in contexts}
        if set(ContextType) - set(context_by_type):
            raise RuntimeError("rewrite context packages are incomplete")
        strategy = StrategyOutput.model_validate(plan.payload)
        route = next(
            (item for item in strategy.creative_routes if item.route_key == candidate.route_key),
            None,
        )
        if route is None:
            raise RuntimeError("rewrite creative route is missing")
        phase2_rows = [(item, revision, "") for item, revision in snapshot_rows]
        _prompt_item, prompt = Phase2Service._require_prompt(phase2_rows, "xhs_writer")
        input_payload = {
            "task": "targeted_compliance_rewrite",
            "iteration": source.version,
            "product_context": context_by_type[ContextType.PRODUCT].payload,
            "policy_context": context_by_type[ContextType.POLICY].payload,
            "trend_context": context_by_type[ContextType.TREND].payload,
            "creative_route": route.model_dump(mode="json"),
            "current_content": source.payload,
            "compliance_findings": [
                {
                    "category": finding.category,
                    "severity": finding.severity,
                    "message": finding.message,
                    "evidence_excerpt": finding.evidence_excerpt,
                    "suggestion": finding.suggestion,
                }
                for finding in findings
            ],
            "revision_instructions": revision_instructions,
        }
        checksum = canonical_checksum(input_payload)
        key = generation_key(
            candidate.id, "compliance_rewrite", source.id, source.version, prompt.id, checksum
        )
        async with self.session_factory() as session:
            existing = await session.scalar(
                select(ContentVersion).where(ContentVersion.generation_key == key)
            )
            if existing is not None:
                return existing.id
        result = await self.llm_gateway.generate(
            LLMRequest(
                brand_id=brand_id,
                run_id=run.id,
                purpose="xhs_writer",
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
            WriterOutput,
        )
        Phase2Service._validate_writer_output(
            result.value,
            route,
            context_by_type[ContextType.PRODUCT].payload,
            phase2_rows,
        )
        async with self._write_guard():
            async with self.session_factory() as session, session.begin():
                locked_candidate = await session.scalar(
                    select(ContentCandidate)
                    .where(
                        ContentCandidate.id == candidate.id,
                        ContentCandidate.brand_id == brand_id,
                    )
                    .with_for_update()
                )
                if locked_candidate is None:
                    raise RuntimeError("rewrite candidate is missing")
                existing = await session.scalar(
                    select(ContentVersion).where(ContentVersion.generation_key == key)
                )
                if existing is not None:
                    locked_candidate.current_version = existing.version
                    return existing.id
                if locked_candidate.current_version != source.version:
                    raise RuntimeError("candidate advanced beyond the requested rewrite source")
                version = ContentVersion(
                    brand_id=brand_id,
                    candidate_id=candidate.id,
                    version=source.version + 1,
                    payload=result.value.model_dump(mode="json"),
                    prompt_revision_id=prompt.id,
                    input_checksum=checksum,
                    generation_key=key,
                )
                session.add(version)
                await session.flush()
                locked_candidate.current_version = version.version
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
                Phase2Service._add_llm_log(
                    session,
                    brand_id,
                    run.id,
                    prompt.id,
                    "xhs_writer_rewrite",
                    result,
                )
                return version.id

    async def save_human_edit(
        self,
        *,
        brand_id: uuid.UUID,
        candidate_id: uuid.UUID,
        edited_content: WriterOutput,
        review_id: uuid.UUID,
    ) -> uuid.UUID:
        async with self.session_factory() as session:
            candidate = await session.scalar(
                select(ContentCandidate).where(
                    ContentCandidate.id == candidate_id,
                    ContentCandidate.brand_id == brand_id,
                )
            )
            if candidate is None:
                raise RuntimeError("human edit candidate is missing")
            source = await session.scalar(
                select(ContentVersion).where(
                    ContentVersion.candidate_id == candidate.id,
                    ContentVersion.version == candidate.current_version,
                )
            )
            plan = await session.scalar(
                select(StrategyPlan).where(StrategyPlan.run_id == candidate.run_id)
            )
            contexts = list(
                await session.scalars(
                    select(RunContextPackage).where(RunContextPackage.run_id == candidate.run_id)
                )
            )
            snapshot_rows = list(
                (
                    await session.execute(
                        select(RegistryItem, RegistryRevision)
                        .join(
                            RunRegistrySnapshot,
                            RunRegistrySnapshot.item_id == RegistryItem.id,
                        )
                        .join(
                            RegistryRevision,
                            RegistryRevision.id == RunRegistrySnapshot.revision_id,
                        )
                        .where(RunRegistrySnapshot.run_id == candidate.run_id)
                    )
                ).all()
            )
        if source is None or plan is None:
            raise RuntimeError("human edit context is incomplete")
        context_by_type = {item.context_type: item for item in contexts}
        if ContextType.PRODUCT not in context_by_type:
            raise RuntimeError("human edit product context is missing")
        strategy = StrategyOutput.model_validate(plan.payload)
        route = next(
            (item for item in strategy.creative_routes if item.route_key == candidate.route_key),
            None,
        )
        if route is None:
            raise RuntimeError("human edit creative route is missing")
        Phase2Service._validate_writer_output(
            edited_content,
            route,
            context_by_type[ContextType.PRODUCT].payload,
            [(item, revision, "") for item, revision in snapshot_rows],
        )
        payload = edited_content.model_dump(mode="json")
        checksum = canonical_checksum(payload)
        key = generation_key(candidate.id, "human_edit", review_id, checksum)
        async with self.session_factory() as session:
            existing = await session.scalar(
                select(ContentVersion).where(ContentVersion.generation_key == key)
            )
            if existing is not None:
                return existing.id
        async with self._write_guard():
            async with self.session_factory() as session, session.begin():
                locked_candidate = await session.scalar(
                    select(ContentCandidate)
                    .where(
                        ContentCandidate.id == candidate.id,
                        ContentCandidate.brand_id == brand_id,
                    )
                    .with_for_update()
                )
                if locked_candidate is None:
                    raise RuntimeError("human edit candidate is missing")
                existing = await session.scalar(
                    select(ContentVersion).where(ContentVersion.generation_key == key)
                )
                if existing is not None:
                    locked_candidate.current_version = existing.version
                    return existing.id
                if locked_candidate.current_version != source.version:
                    raise RuntimeError("candidate advanced beyond the human edit source")
                version = ContentVersion(
                    brand_id=brand_id,
                    candidate_id=candidate.id,
                    version=source.version + 1,
                    payload=payload,
                    prompt_revision_id=source.prompt_revision_id,
                    input_checksum=checksum,
                    generation_key=key,
                )
                session.add(version)
                await session.flush()
                locked_candidate.current_version = version.version
                for claim_id in edited_content.cited_claim_revision_ids:
                    session.add(
                        ContentClaimUsage(
                            brand_id=brand_id,
                            content_version_id=version.id,
                            claim_revision_id=claim_id,
                            usage_type="explicit",
                            content_excerpt="",
                        )
                    )
                return version.id

    async def get_report(
        self, *, brand_id: uuid.UUID, report_id: uuid.UUID
    ) -> ComplianceReportRead:
        async with self.session_factory() as session:
            report = await session.scalar(
                select(ComplianceReport).where(
                    ComplianceReport.id == report_id,
                    ComplianceReport.brand_id == brand_id,
                )
            )
            if report is None:
                raise RuntimeError("compliance report not found")
            findings = list(
                await session.scalars(
                    select(ComplianceFinding)
                    .where(ComplianceFinding.report_id == report.id)
                    .order_by(ComplianceFinding.created_at)
                )
            )
        return ComplianceReportRead(
            id=report.id,
            content_version_id=report.content_version_id,
            deterministic_pass=report.deterministic_pass,
            semantic_pass=report.semantic_pass,
            has_blockers=report.has_blockers,
            summary=report.summary,
            findings=[ComplianceFindingRead.model_validate(item) for item in findings],
        )

    @staticmethod
    def _deterministic_findings(
        *,
        writer: WriterOutput,
        product_context: ProductContextOutput,
        snapshot_rows: list[tuple[RegistryItem, RegistryRevision]],
    ) -> list[dict[str, Any]]:
        text = "\n".join(
            [
                *writer.title_options,
                writer.body,
                writer.visual_brief.cover_text,
                *writer.visual_brief.shot_list,
                writer.media_plan.preferred_generation_prompt,
                writer.media_plan.alternate_generation_prompt,
                *writer.media_plan.image_sequence,
                *writer.media_plan.shot_list,
                writer.media_plan.voiceover,
                *writer.media_plan.on_screen_text,
                *writer.media_plan.shooting_notes,
                *writer.tags,
            ]
        )
        findings: list[dict[str, Any]] = []

        def add(
            category: str,
            severity: str,
            message: str,
            excerpt: str,
            suggestion: str,
            **references: Any,
        ) -> None:
            findings.append(
                {
                    "category": category,
                    "severity": severity,
                    "message": message,
                    "source": "deterministic",
                    "evidence_excerpt": excerpt,
                    "suggestion": suggestion,
                    "evidence": {},
                    **references,
                }
            )

        for term in MEDICAL_TERMS:
            unsafe_occurrences = [
                match
                for match in re.finditer(re.escape(term), text)
                if not ComplianceService._medical_term_is_negated(text, match.start())
            ]
            if unsafe_occurrences:
                add(
                    "medical_claim",
                    "blocker",
                    f"发现明确医疗化表达：{term}",
                    term,
                    "删除医疗结论，改为已验证的消费级非医疗表述。",
                )
        for pattern in FALSE_EXPERIENCE_PATTERNS:
            match = pattern.search(text)
            if match:
                add(
                    "false_experience",
                    "blocker",
                    "品牌官方内容疑似伪造个人使用经历。",
                    match.group(0),
                    "改为品牌客观介绍，不使用亲测、使用周期或身体改善叙事。",
                )
        for term in ADVERTISING_TERMS:
            if term in text:
                add(
                    "advertising",
                    "warning",
                    f"表达具有较强保证或促销感：{term}",
                    term,
                    "改为克制、可验证的描述。",
                )

        cited_claims = set(writer.cited_claim_revision_ids)
        allowed_claims = {item.claim_revision_id for item in product_context.allowed_claims}
        for claim_id in cited_claims - allowed_claims:
            add(
                "claim_traceability",
                "blocker",
                "内容引用了 Product Context 未允许的 Claim。",
                str(claim_id),
                "删除该表达或补充经 Reviewer 激活的 Claim 与证据。",
                claim_revision_id=claim_id,
            )
        for item, revision in snapshot_rows:
            if item.registry_type != RegistryType.PRODUCT_CLAIM:
                continue
            for expression in revision.payload.get("forbidden_expressions", []):
                if expression in text:
                    add(
                        "forbidden_claim_expression",
                        "blocker",
                        "内容使用了 Product Claim 明确禁止的表达。",
                        expression,
                        "使用该 Claim 的 allowed expression，或删除相关效果描述。",
                        claim_revision_id=revision.id,
                    )
            if revision.id not in cited_claims:
                for expression in revision.payload.get("allowed_expressions", []):
                    if expression in text:
                        add(
                            "claim_traceability",
                            "blocker",
                            "正文出现 Claim 表达但未声明 Claim 引用。",
                            expression,
                            "补充正确 Claim Revision 引用或删除该表达。",
                            claim_revision_id=revision.id,
                        )
        return findings

    @staticmethod
    def _medical_term_is_negated(text: str, term_start: int) -> bool:
        """Recognize explicit non-medical disclaimers around a medical term.

        The deterministic layer must block affirmative claims, but phrases such as
        “不用于诊断、治疗，也不能替代医生” are required safety disclaimers. Limit the
        check to the same short clause and reset it after adversative wording so that
        “不能诊断，但可以治疗” still blocks the latter claim.
        """
        clause_start = max([text.rfind(mark, 0, term_start) for mark in "。！？；\n"] + [-1])
        prefix = text[clause_start + 1 : term_start]
        for boundary in ("但是", "不过", "然而", "但"):
            index = prefix.rfind(boundary)
            if index >= 0:
                prefix = prefix[index + len(boundary) :]
        return bool(
            re.search(
                r"(?:不用于|不得用于|不可用于|不能用于|不作|不具备|不提供|"
                r"不涉及|不承诺|并非|没有|无法|不能|不可|不得|非|无|不)"
                r"[^，。！？；\n]{0,16}$",
                prefix,
            )
        )

    @staticmethod
    def _require_prompt(
        rows: list[tuple[RegistryItem, RegistryRevision]],
    ) -> RegistryRevision:
        for item, revision in rows:
            if (
                item.registry_type == RegistryType.PROMPT_TEMPLATE
                and item.stable_key == PROMPT_COMPLIANCE
            ):
                return revision
        raise RuntimeError("required prompt revision is missing from run snapshot: xhs_compliance")

    @staticmethod
    def _validate_semantic_references(
        output: ComplianceSemanticOutput,
        rows: list[tuple[RegistryItem, RegistryRevision]],
    ) -> None:
        rule_ids = {
            revision.id
            for item, revision in rows
            if item.registry_type == RegistryType.PLATFORM_RULE
        }
        claim_ids = {
            revision.id
            for item, revision in rows
            if item.registry_type == RegistryType.PRODUCT_CLAIM
        }
        for finding in output.findings:
            if finding.rule_revision_id is not None and finding.rule_revision_id not in rule_ids:
                raise ValueError("semantic compliance referenced a rule outside run snapshot")
            if finding.claim_revision_id is not None and finding.claim_revision_id not in claim_ids:
                raise ValueError("semantic compliance referenced a claim outside run snapshot")

    @asynccontextmanager
    async def _write_guard(self) -> AsyncIterator[None]:
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
