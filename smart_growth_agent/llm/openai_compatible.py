from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, TypeVar
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ValidationError

from smart_growth_agent.config import Settings
from smart_growth_agent.domain.errors import DomainError
from smart_growth_agent.llm.types import LLMRequest, LLMResult, LLMUsage

T = TypeVar("T", bound=BaseModel)


class LLMGatewayError(DomainError):
    """A provider failure with an operator-safe message."""

    def __init__(
        self,
        message: str,
        *,
        provider_status: int | None = None,
        provider_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider_status = provider_status
        self.provider_code = provider_code


class OpenAICompatibleGateway:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if settings.openai_api_key is None or settings.openai_model is None:
            raise ValueError("OPENAI_API_KEY and OPENAI_MODEL must be configured")
        self.settings = settings
        self.client = client or httpx.AsyncClient(
            base_url=settings.openai_base_url.rstrip("/"),
            timeout=settings.llm_request_timeout_seconds,
            headers={"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"},
        )
        self._owns_client = client is None

    async def generate(self, request: LLMRequest, response_model: type[T]) -> LLMResult[T]:
        from smart_growth_agent.llm.policy import validate_code_contract

        validate_code_contract(request, response_model)
        model = request.model or self.settings.openai_model
        assert model is not None
        schema = self._strict_json_schema(response_model.model_json_schema())
        payload: dict[str, Any] = {
            "model": model,
            "messages": [message.model_dump() for message in request.messages],
            "temperature": request.temperature,
        }
        if urlparse(self.settings.openai_base_url).hostname == "api.deepseek.com":
            payload = self._schema_prompt_fallback(
                payload, schema=schema, schema_name=response_model.__name__
            )
            payload["response_format"] = {"type": "json_object"}
            payload["thinking"] = {"type": "disabled"}
        elif self._uses_minimax_text_json(model):
            # MiniMax M2-family reasoning models do not support response_format/json_schema.
            # Their OpenAI-compatible endpoint returns JSON as ordinary assistant text,
            # optionally wrapped in <think> tags. Keep the provider request compatible
            # and enforce the contract locally with Pydantic.
            payload["temperature"] = min(max(request.temperature, 0.01), 1)
            payload["reasoning_split"] = True
            payload = self._schema_prompt_fallback(
                payload,
                schema=schema,
                schema_name=response_model.__name__,
            )
        else:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "strict": True,
                    "schema": schema,
                },
            }
        if self.settings.llm_max_output_tokens is not None:
            payload["max_tokens"] = self.settings.llm_max_output_tokens
        parsed, body, latency_ms, provider_attempts = await self._request_and_parse(
            payload, response_model
        )
        usage = body.get("usage", {})
        choice = body.get("choices", [{}])[0]
        completion_details = usage.get("completion_tokens_details") or {}
        return LLMResult[T](
            value=parsed,
            provider="openai-compatible",
            model=body.get("model", model),
            usage=LLMUsage(
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
            ),
            latency_ms=latency_ms,
            provider_request_id=body.get("id"),
            raw_metadata={
                "finish_reason": choice.get("finish_reason"),
                "reasoning_tokens": completion_details.get("reasoning_tokens"),
                "structured_output_mode": (
                    "prompt_json_schema"
                    if self._uses_minimax_text_json(model)
                    else "json_object_local_validation"
                    if payload.get("response_format", {}).get("type") == "json_object"
                    else "native_json_schema"
                ),
                "provider_attempts": provider_attempts,
            },
        )

    async def _request_and_parse(
        self, payload: dict[str, Any], response_model: type[T]
    ) -> tuple[T, dict[str, Any], int, int]:
        overall_started = time.perf_counter()
        last_error: Exception | None = None
        used_schema_fallback = False
        used_parse_repair = False
        network_failures = 0
        provider_attempts = 0
        total_input_tokens = 0
        total_output_tokens = 0
        input_usage_reported = False
        output_usage_reported = False
        for _attempt in range(5):
            try:
                slot = None
                if self.settings.llm_budget_path:
                    from smart_growth_agent.llm.budget import reserve

                    try:
                        slot = reserve(
                            self.settings.llm_budget_path,
                            self.settings.llm_max_calls,
                            payload["model"],
                        )
                    except (RuntimeError, OSError, ValueError, KeyError, TypeError):
                        raise LLMGatewayError(
                            "模型请求预算耗尽或台账不可用；已在发送前停止。"
                        ) from None
                try:
                    response = await self.client.post("/chat/completions", json=payload)
                except (httpx.TransportError, asyncio.CancelledError):
                    if slot is not None:
                        from smart_growth_agent.llm.budget import complete

                        complete(self.settings.llm_budget_path, slot, 0, None)
                    raise
                if slot is not None:
                    from smart_growth_agent.llm.budget import complete

                    try:
                        budget_body = response.json()
                        if not isinstance(budget_body, dict):
                            budget_body = {}
                    except ValueError:
                        budget_body = {}
                    complete(self.settings.llm_budget_path, slot, response.status_code, budget_body)
                response.raise_for_status()
                try:
                    body = response.json()
                    if not isinstance(body, dict):
                        raise ValueError("provider body is not an object")
                    self._raise_for_provider_body(body)
                    provider_attempts += 1
                    usage = body.get("usage") or {}
                    input_tokens = usage.get("prompt_tokens")
                    output_tokens = usage.get("completion_tokens")
                    if isinstance(input_tokens, int):
                        total_input_tokens += input_tokens
                        input_usage_reported = True
                    if isinstance(output_tokens, int):
                        total_output_tokens += output_tokens
                        output_usage_reported = True
                    choice = body["choices"][0]
                    if choice.get("finish_reason") == "length":
                        raise LLMGatewayError(
                            "模型输出因长度上限被截断，无法形成完整 JSON；"
                            "请减少单次资料量或提高该模型的输出额度。"
                        )
                    content = self._message_content(choice["message"])
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    raise LLMGatewayError(
                        "模型服务返回了无法识别的响应格式，请检查 Base URL 和模型兼容性。"
                    ) from exc
                try:
                    aggregated_body = dict(body)
                    aggregated_usage = dict(body.get("usage") or {})
                    aggregated_usage["prompt_tokens"] = (
                        total_input_tokens if input_usage_reported else None
                    )
                    aggregated_usage["completion_tokens"] = (
                        total_output_tokens if output_usage_reported else None
                    )
                    aggregated_body["usage"] = aggregated_usage
                    return (
                        self._parse_typed_content(content, response_model),
                        aggregated_body,
                        round((time.perf_counter() - overall_started) * 1000),
                        provider_attempts,
                    )
                except ValidationError as validation_error:
                    if used_parse_repair:
                        raise LLMGatewayError(
                            "模型已按当前供应商的 JSON 格式要求重试，但返回字段仍不符合 "
                            f"{response_model.__name__}；请检查模型名称，或减少本次资料后重试。"
                        ) from validation_error
                    payload = self._repair_payload(
                        payload,
                        content,
                        validation_error,
                        response_model=response_model,
                    )
                    used_parse_repair = True
                    last_error = validation_error
                    continue
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if isinstance(exc, httpx.HTTPStatusError):
                    status_code = exc.response.status_code
                    if (
                        status_code in {400, 422}
                        and not used_schema_fallback
                        and "json_schema" in payload.get("response_format", {})
                    ):
                        schema_block = payload["response_format"]["json_schema"]
                        payload = self._schema_prompt_fallback(
                            payload,
                            schema=schema_block["schema"],
                            schema_name=schema_block["name"],
                        )
                        used_schema_fallback = True
                        continue
                    if status_code < 500 and status_code != 429:
                        raise self._provider_http_error(exc.response) from exc
                if self.settings.llm_no_network_retry:
                    if isinstance(exc, httpx.HTTPStatusError):
                        raise self._provider_http_error(exc.response) from None
                    raise LLMGatewayError("模型请求结果未知，已停止自动重试。") from None
                network_failures += 1
                if network_failures < 3:
                    await asyncio.sleep(2 ** (network_failures - 1))
                    continue
                break
        if isinstance(last_error, httpx.HTTPStatusError):
            raise self._provider_http_error(last_error.response) from last_error
        if isinstance(last_error, httpx.TimeoutException):
            raise LLMGatewayError("模型服务响应超时，请稍后重试或更换模型。") from last_error
        raise LLMGatewayError("无法连接模型服务，请检查 Base URL、网络和服务状态。") from last_error

    @staticmethod
    def _provider_http_error(response: httpx.Response) -> LLMGatewayError:
        status_code = response.status_code
        provider_code: str | None = None
        try:
            body = response.json()
            code = body.get("base_resp", {}).get("status_code")
            code = code if code is not None else body.get("error", {}).get("code")
            provider_code = str(code) if code is not None else None
        except (ValueError, AttributeError, TypeError):
            provider_code = None

        if status_code == 401 or provider_code == "1004":
            message = "API Key 无效、已过期或没有访问该模型的权限。"
        elif status_code == 402 or provider_code == "1008":
            message = "模型账户余额或 Token Plan 额度不足，请先在供应商控制台补充资源。"
        elif status_code == 403:
            message = "模型服务拒绝访问，请检查 API Key 权限、账户或地区限制。"
        elif status_code == 404:
            message = "模型接口或模型 ID 不存在，请检查 Base URL 和模型名称。"
        elif status_code == 429 or provider_code == "1002":
            message = "模型请求达到频率或额度限制，请稍后重试。"
        elif status_code in {400, 422}:
            message = "模型不接受当前请求；请检查模型 ID 及 JSON Schema 结构化输出兼容性。"
        elif status_code >= 500:
            message = "模型供应商服务暂时不可用，请稍后重试。"
        else:
            message = f"模型服务请求失败（供应商状态 {status_code}）。"
        return LLMGatewayError(
            message,
            provider_status=status_code,
            provider_code=provider_code,
        )

    @staticmethod
    def _strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
        """Make Pydantic's schema compatible with strict structured outputs."""

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                # Only closed Pydantic models have explicit properties. Mapping fields
                # such as dict[str, float] use additionalProperties as their value
                # schema and must remain open to arbitrary keys.
                if "properties" in value:
                    properties = value.get("properties", {})
                    value["additionalProperties"] = False
                    value["required"] = list(properties)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        strict_schema = json.loads(json.dumps(schema))
        visit(strict_schema)
        return strict_schema

    @staticmethod
    def _repair_payload(
        payload: dict[str, Any],
        invalid_content: str,
        error: ValidationError,
        *,
        response_model: type[BaseModel],
    ) -> dict[str, Any]:
        repaired = dict(payload)
        schema = OpenAICompatibleGateway._strict_json_schema(response_model.model_json_schema())
        concise_errors = [
            {
                "path": ".".join(str(part) for part in item["loc"]),
                "type": item["type"],
                "message": item["msg"],
            }
            for item in error.errors(include_input=False, include_url=False)
        ]
        repaired["messages"] = [
            *payload["messages"],
            {"role": "assistant", "content": invalid_content},
            {
                "role": "user",
                "content": (
                    "上一个回答未通过本地结构校验。请根据下面的错误和完整 Schema "
                    "重新输出整个 JSON 对象；只输出 JSON，不要解释、Markdown 或代码围栏。"
                    "\n校验错误："
                    + json.dumps(concise_errors, ensure_ascii=False, separators=(",", ":"))
                    + "\nJSON Schema："
                    + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
                ),
            },
        ]
        return repaired

    @staticmethod
    def _parse_typed_content(content: str, response_model: type[T]) -> T:
        """Parse final JSON while tolerating provider reasoning and Markdown wrappers."""
        try:
            return response_model.model_validate_json(content)
        except ValidationError as direct_error:
            cleaned = re.sub(r"<think\b[^>]*>.*?</think>", "", content, flags=re.DOTALL | re.I)
            cleaned = cleaned.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
                cleaned = re.sub(r"\s*```$", "", cleaned).strip()
            decoder = json.JSONDecoder()
            for index, character in enumerate(cleaned):
                if character != "{":
                    continue
                try:
                    value, _end = decoder.raw_decode(cleaned[index:])
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    return response_model.model_validate(value)
            raise direct_error

    def _uses_minimax_text_json(self, model: str) -> bool:
        """Use prompt-constrained JSON for MiniMax reasoning models.

        MiniMax-Text-01 is the documented exception that supports response_format.
        """
        hostname = (urlparse(self.settings.openai_base_url).hostname or "").lower()
        normalized_model = model.strip().lower()
        is_minimax = "minimax" in hostname or normalized_model.startswith("minimax-")
        return is_minimax and normalized_model != "minimax-text-01"

    @staticmethod
    def _message_content(message: dict[str, Any]) -> str:
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                text = block.get("text") or block.get("content")
                if isinstance(text, str):
                    text_parts.append(text)
            if text_parts:
                return "\n".join(text_parts)
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            for call in tool_calls:
                arguments = (
                    call.get("function", {}).get("arguments") if isinstance(call, dict) else None
                )
                if isinstance(arguments, str) and arguments.strip():
                    return arguments
        raise ValueError("assistant message has no parseable content")

    @staticmethod
    def _raise_for_provider_body(body: dict[str, Any]) -> None:
        base_resp = body.get("base_resp")
        if not isinstance(base_resp, dict):
            return
        code = base_resp.get("status_code")
        if code in (None, 0, "0"):
            return
        provider_code = str(code)
        if provider_code == "1004":
            message = "API Key 无效、已过期或没有访问该模型的权限。"
        elif provider_code == "1008":
            message = "模型账户余额或 Token Plan 额度不足，请先在供应商控制台补充资源。"
        elif provider_code == "1002":
            message = "模型请求达到频率或额度限制，请稍后重试。"
        elif provider_code == "1039":
            message = "模型输入或输出超过 Token 上限，请减少单次资料量。"
        elif provider_code == "1027":
            message = "MiniMax 未能生成有效输出，请减少资料量或调整模型后重试。"
        else:
            message = f"模型供应商返回业务错误（代码 {provider_code}）。"
        raise LLMGatewayError(message, provider_code=provider_code)

    @staticmethod
    def _schema_prompt_fallback(
        payload: dict[str, Any],
        *,
        schema: dict[str, Any],
        schema_name: str,
    ) -> dict[str, Any]:
        """Keep typed validation when a provider lacks native json_schema support."""
        fallback = {key: value for key, value in payload.items() if key != "response_format"}
        top_level_keys = list(schema.get("properties", {}))
        fallback["messages"] = [
            *payload["messages"],
            {
                "role": "user",
                "content": (
                    f"输出协议（{schema_name}，优先级高于前文中的类型名称）："
                    "只返回一个完整 JSON 对象，不要 Markdown、代码围栏、解释或额外文字。"
                    f"顶层字段必须且只能是：{json.dumps(top_level_keys, ensure_ascii=False)}。"
                    "缺少信息时使用 Schema 允许的空数组、空对象、null 或说明文字，"
                    "不要省略必填字段，也不要自行增加字段。输出必须满足以下 JSON Schema："
                    + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
                ),
            },
        ]
        return fallback

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()
