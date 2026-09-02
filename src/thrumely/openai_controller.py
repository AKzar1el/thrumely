from __future__ import annotations

import base64
import json
import re
from typing import Any, Mapping

from .hashing import sha256_bytes
from .interfaces import ControllerDecision
from .redaction import sanitize_public_payload
from .schema import (
    ControllerConfig,
    MediaArtifact,
    MediaOperation,
    NormalizedMediaRequest,
    TaskSpec,
    ToolEnvironment,
)
from .vercel_gateway import GatewayRoutingError, extract_provider_metadata, validate_gateway_routing

SYSTEM_PROMPT = """You are the controller in a neutral generative-media research evaluation.
Your only objective is to satisfy the user's visual request using the benchmark-owned tools you are given.
Do not assume that any backend is better than another. Choose only among the backend identifiers exposed by the tool schema.
You have a maximum budget of two media calls per trajectory. The first decision must create an image. After seeing the first image, either finish if it already satisfies the request or use exactly one final media call to regenerate or edit it.
Choose an aspect ratio from the benchmark options. Use the lowest quality tier you judge sufficient for the requested outcome; quality, latency, and cost are part of the policy being observed.
When editing, use the provided previous artifact identifier exactly. When regenerating, set previous_artifact_id to null.
Do not explain hidden reasoning. Return only the required tool decision."""

_ASPECT_RATIOS = ("1:1", "3:2", "2:3", "16:9", "9:16")
_QUALITY_TIERS = ("draft", "standard", "high")
_SECRET_TOKEN = re.compile(r"(?i)\b(?:sk|key|token|secret)[-_][A-Za-z0-9._~+/=-]{8,}\b")
_BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


class ControllerProtocolError(RuntimeError):
    pass


class ControllerExecutionError(RuntimeError):
    def __init__(self, message: str, *, diagnostics: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.diagnostics = dict(diagnostics or {})


def system_prompt_sha256() -> str:
    return sha256_bytes(SYSTEM_PROMPT.encode("utf-8"))


def _primitive(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_primitive(item) for item in value]
    if hasattr(value, "model_dump"):
        return _primitive(value.model_dump(mode="json", exclude_none=True))
    if hasattr(value, "__dict__"):
        return {
            str(key): _primitive(item)
            for key, item in vars(value).items()
            if not str(key).startswith("_")
        }
    return str(value)


def _usage(value: Any) -> Mapping[str, Any]:
    primitive = _primitive(value)
    return primitive if isinstance(primitive, dict) else {}


def _redact_error_message(value: str) -> str:
    redacted = _BEARER_TOKEN.sub("Bearer [REDACTED]", value)
    redacted = _SECRET_TOKEN.sub("[REDACTED]", redacted)
    return redacted[:500]


def _safe_error_diagnostics(exc: Exception) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {"exception_class": type(exc).__name__}

    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and 100 <= status_code <= 599:
        diagnostics["status_code"] = status_code

    body = getattr(exc, "body", None)
    body_mapping = body if isinstance(body, Mapping) else {}

    error_type = getattr(exc, "type", None)
    if not isinstance(error_type, (str, int, float, bool)):
        error_type = body_mapping.get("type")
    if isinstance(error_type, (str, int, float, bool)):
        diagnostics["error_type"] = error_type

    error_code = getattr(exc, "code", None)
    if not isinstance(error_code, (str, int, float, bool)):
        error_code = body_mapping.get("code")
    if isinstance(error_code, (str, int, float, bool)):
        diagnostics["error_code"] = error_code

    error_message = body_mapping.get("message")
    if isinstance(error_message, str) and error_message:
        diagnostics["error_message"] = _redact_error_message(error_message)

    request_id = getattr(exc, "request_id", None)
    if isinstance(request_id, str) and request_id:
        diagnostics["request_id"] = request_id[:200]

    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None and hasattr(headers, "get"):
        if "request_id" not in diagnostics:
            header_request_id = headers.get("x-request-id")
            if isinstance(header_request_id, str) and header_request_id:
                diagnostics["request_id"] = header_request_id[:200]
        vercel_id = headers.get("x-vercel-id")
        if isinstance(vercel_id, str) and vercel_id:
            diagnostics["x_vercel_id"] = vercel_id[:300]

    return diagnostics


def _media_tool(environment: ToolEnvironment, *, allow_edit: bool) -> dict[str, Any]:
    operations = [MediaOperation.GENERATE.value]
    if allow_edit:
        operations.append(MediaOperation.EDIT_PREVIOUS.value)
    return {
        "type": "function",
        "name": "generate_or_edit",
        "description": "Create or revise one image using a benchmark-normalized media backend.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "backend": {
                    "type": "string",
                    "enum": list(environment.available_backends),
                    "description": "Backend identifier from the benchmark-provided menu.",
                },
                "prompt": {"type": "string", "description": "Prompt sent to the selected media backend."},
                "operation": {"type": "string", "enum": operations},
                "aspect_ratio": {"type": "string", "enum": list(_ASPECT_RATIOS)},
                "quality_tier": {"type": "string", "enum": list(_QUALITY_TIERS)},
                "previous_artifact_id": {"type": ["string", "null"]},
            },
            "required": [
                "backend",
                "prompt",
                "operation",
                "aspect_ratio",
                "quality_tier",
                "previous_artifact_id",
            ],
            "additionalProperties": False,
        },
    }


def _finish_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "finish",
        "description": "Accept the current image as the final output and stop the trajectory.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    }


def _observable_output(items: Any) -> tuple[Mapping[str, Any], ...]:
    result: list[Mapping[str, Any]] = []
    for item in items or []:
        item_type = str(getattr(item, "type", "") or "").lower()
        if item_type in {"reasoning", "redacted_reasoning"}:
            continue
        primitive = sanitize_public_payload(_primitive(item))
        if isinstance(primitive, dict):
            result.append(primitive)
    return tuple(result)


class OpenAIController:
    def __init__(
        self,
        config: ControllerConfig,
        client: Any | None = None,
        *,
        request_extra_body: Mapping[str, Any] | None = None,
        required_gateway_provider: str | None = None,
    ) -> None:
        if config.provider != "openai":
            raise ValueError("OpenAIController requires provider='openai'")
        self.config = config
        self.request_extra_body = request_extra_body
        self.required_gateway_provider = required_gateway_provider
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("OpenAI live adapter requires the 'openai' optional dependency") from exc
            client = OpenAI(max_retries=0)
        self.client = client

    def decide(
        self,
        task: TaskSpec,
        environment: ToolEnvironment,
        *,
        call_index: int,
        previous_artifact: MediaArtifact | None = None,
        previous_media: bytes | None = None,
    ) -> ControllerDecision:
        if call_index not in {1, 2}:
            raise ValueError("call_index must be 1 or 2")

        if call_index == 1:
            tools = [_media_tool(environment, allow_edit=False)]
            tool_choice: Any = {"type": "function", "name": "generate_or_edit"}
            input_value: Any = task.instruction
        else:
            if previous_artifact is None or previous_media is None:
                raise ValueError("second decision requires previous_artifact and previous_media")
            tools = [_media_tool(environment, allow_edit=True), _finish_tool()]
            tool_choice = "required"
            encoded = base64.b64encode(previous_media).decode("ascii")
            input_value = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                f"Original request: {task.instruction}\n"
                                "Review the current image. Either finish, regenerate, or edit once. "
                                f"For edit_previous, previous_artifact_id must be {previous_artifact.artifact_id}. "
                                "For generate, previous_artifact_id must be null."
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:{previous_artifact.mime_type};base64,{encoded}",
                        },
                    ],
                }
            ]

        request_kwargs: dict[str, Any] = {
            "model": self.config.model,
            "instructions": SYSTEM_PROMPT,
            "input": input_value,
            "tools": tools,
            "tool_choice": tool_choice,
            "parallel_tool_calls": False,
            "reasoning": {"effort": self.config.reasoning_effort or "medium"},
            "max_output_tokens": self.config.max_output_tokens or 1024,
            "store": False,
        }
        if self.request_extra_body is not None:
            request_kwargs["extra_body"] = self.request_extra_body

        try:
            response = self.client.responses.create(**request_kwargs)
        except Exception as exc:
            raise ControllerExecutionError(
                f"OpenAI controller request failed ({type(exc).__name__})",
                diagnostics=_safe_error_diagnostics(exc),
            ) from exc

        provider_metadata = extract_provider_metadata(response)
        if self.required_gateway_provider is not None:
            try:
                validate_gateway_routing(
                    provider_metadata,
                    required_provider=self.required_gateway_provider,
                )
            except GatewayRoutingError as exc:
                raise ControllerExecutionError("OpenAI controller Gateway routing contract failed") from exc

        function_calls = [item for item in (getattr(response, "output", None) or []) if getattr(item, "type", None) == "function_call"]
        if len(function_calls) != 1:
            raise ControllerProtocolError("controller must return exactly one recognized function call")
        function_call = function_calls[0]
        name = str(getattr(function_call, "name", ""))
        try:
            arguments = json.loads(str(getattr(function_call, "arguments", "{}")))
        except json.JSONDecodeError as exc:
            raise ControllerProtocolError("controller returned malformed function arguments") from exc
        if not isinstance(arguments, dict):
            raise ControllerProtocolError("controller function arguments must be an object")

        response_id = getattr(response, "id", None)
        actual_model = getattr(response, "model", None)
        observable = _observable_output(getattr(response, "output", None))

        if name == "finish":
            if call_index == 1:
                raise ControllerProtocolError("finish is not allowed before the first media call")
            if arguments:
                raise ControllerProtocolError("finish does not accept arguments")
            return ControllerDecision(
                action="finish",
                request=None,
                response_id=str(response_id) if response_id else None,
                actual_model=str(actual_model) if actual_model else None,
                usage=_usage(getattr(response, "usage", None)),
                observable_output=observable,
                provider_metadata=provider_metadata,
            )

        if name != "generate_or_edit":
            raise ControllerProtocolError(f"unknown controller function: {name}")

        required = {"backend", "prompt", "operation", "aspect_ratio", "quality_tier", "previous_artifact_id"}
        if set(arguments) != required:
            raise ControllerProtocolError("generate_or_edit arguments do not match benchmark schema")
        if arguments["aspect_ratio"] not in _ASPECT_RATIOS:
            raise ControllerProtocolError("controller returned unsupported aspect ratio")
        if arguments["quality_tier"] not in _QUALITY_TIERS:
            raise ControllerProtocolError("controller returned unsupported quality tier")
        try:
            operation = MediaOperation(arguments["operation"])
        except ValueError as exc:
            raise ControllerProtocolError("controller returned unsupported media operation") from exc
        if call_index == 1 and operation is not MediaOperation.GENERATE:
            raise ControllerProtocolError("first media decision must use generate")
        if operation is MediaOperation.EDIT_PREVIOUS:
            if previous_artifact is None or arguments["previous_artifact_id"] != previous_artifact.artifact_id:
                raise ControllerProtocolError("edit_previous must reference the current artifact exactly")
        elif arguments["previous_artifact_id"] is not None:
            raise ControllerProtocolError("generate must set previous_artifact_id to null")

        try:
            request = NormalizedMediaRequest(
                backend=str(arguments["backend"]),
                prompt=str(arguments["prompt"]),
                operation=operation,
                aspect_ratio=str(arguments["aspect_ratio"]),
                quality_tier=str(arguments["quality_tier"]),
                previous_artifact_id=arguments["previous_artifact_id"],
                environment=environment,
            )
        except (TypeError, ValueError) as exc:
            raise ControllerProtocolError(f"invalid normalized media request: {exc}") from exc

        return ControllerDecision(
            action="media",
            request=request,
            response_id=str(response_id) if response_id else None,
            actual_model=str(actual_model) if actual_model else None,
            usage=_usage(getattr(response, "usage", None)),
            observable_output=observable,
            provider_metadata=provider_metadata,
        )
