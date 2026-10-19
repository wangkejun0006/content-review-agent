from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from smart_growth_agent.schemas.compliance import ComplianceSemanticOutput
from smart_growth_agent.schemas.evidence_import import EvidenceImportAIOutput
from smart_growth_agent.schemas.feedback import FeedbackOutput
from smart_growth_agent.schemas.phase2 import (
    ProductContextOutput,
    StrategyOutput,
    WriterOutput,
)
from smart_growth_agent.schemas.platform_rule_import import PlatformRuleAIOutput
from smart_growth_agent.schemas.product_import import ProductImportAIOutput
from smart_growth_agent.schemas.scoring import ScoringOutput

T = TypeVar("T", bound=BaseModel)


LLM_OUTPUT_CONTRACTS: dict[str, type[BaseModel]] = {
    "product_registry_import": ProductImportAIOutput,
    "evidence_registry_import": EvidenceImportAIOutput,
    "platform_rule_import": PlatformRuleAIOutput,
    "xhs_product_context": ProductContextOutput,
    "xhs_strategy": StrategyOutput,
    "xhs_writer": WriterOutput,
    "xhs_compliance_semantic": ComplianceSemanticOutput,
    "xhs_scoring": ScoringOutput,
    "xhs_feedback": FeedbackOutput,
}


def contract_mismatch(
    *,
    purpose: str,
    response_model: type[BaseModel],
    prompt_schema_name: str | None,
) -> str | None:
    expected = LLM_OUTPUT_CONTRACTS.get(purpose)
    if expected is None:
        return f"Agent 用途 {purpose} 尚未注册结构化输出契约"
    if response_model is not expected:
        return (
            f"Agent 用途 {purpose} 的代码输出契约应为 {expected.__name__}，"
            f"实际使用 {response_model.__name__}"
        )
    if prompt_schema_name != expected.__name__:
        return (
            f"Agent 用途 {purpose} 的 Prompt 输出契约应为 {expected.__name__}，"
            f"实际配置 {prompt_schema_name or '空值'}"
        )
    return None
