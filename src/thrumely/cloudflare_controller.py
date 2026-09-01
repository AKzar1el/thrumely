from __future__ import annotations

import base64
import json
import os
from typing import Any, Mapping
from urllib.request import Request, urlopen

from .interfaces import ControllerDecision, ControllerExecutionError, ControllerProtocolError
from .openai_controller import SYSTEM_PROMPT
from .schema import (
    ControllerConfig,
    MediaArtifact,
    MediaOperation,
    NormalizedMediaRequest,
    TaskSpec,
    ToolEnvironment,
)

_BASE_URL = "https://api.cloudflare.com/client/v4"
_ASPECT_RATIOS = ("1:1", "3:2", "2:3", "16:9", "9:16")
_QUALITY_TIERS = ("draft", "standard", "high")


class _UrllibTransport:
    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        json_payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        body = json.dumps(json_payload).encode("utf-8")
        request_headers = dict(headers)
        request_headers["Content-Type"] = "application/json"
        request_headers["Accept"] = "application/json"
        request = Request(url, data=body, headers=request_headers, method="POST")
        with urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))


def _media_schema(environment: ToolEnvironment, *, allow_edit: bool) -> dict[str, Any]:
    operations = [MediaOperation.GENERATE.value]
    if allow_edit:
        operations.append(MediaOperation.EDIT_PREVIOUS.value)
    return {
        "type": "object",
        "properties": {
            "backend": {
                "type": "string",
                "enum": list(environment.available_backends),
                "description": "Backend identifier from the benchmark-provided menu.",
            },
            "prompt": {
                "type": "string",
                "description": "Prompt sent to the selected media backend.",
            },
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
    }


def _media_tool(environment: ToolEnvironment, *, allow_edit: bool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "generate_or_edit",
            "description": "Create or revise one image using a benchmark-normalized media backend.",
            "strict": True,
            "parameters": _media_schema(environment, allow_edit=allow_edit),
        },
    }


def _finish_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Accept the current image as the final output and stop the trajectory.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    }


def _parse_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError as exc:
        raise ControllerProtocolError("controller returned malformed function arguments") from exc
    if not isinstance(parsed, dict):
        raise ControllerProtocolError("controller function arguments must be an object")
    return parsed


def _usage(response: Mapping[str, Any]) -> Mapping[str, Any]:
    usage = response.get("usage")
    return dict(usage) if isinstance(usage, Mapping) else {}


class CloudflareController:
    def __init__(
        self,
        config: ControllerConfig,
        *,
        account_id: str | None = None,
        api_token: str | None = None,
        transport: Any | None = None,
        base_url: str = _BASE_URL,
    ) -> None:
        if config.provider != "cloudflare":
            raise ValueError("CloudflareController requires provider='cloudflare'")
        self.config = config
        self.account_id = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        self.api_token = api_token or os.environ.get("CLOUDFLARE_API_TOKEN")
        self.transport = transport or _UrllibTransport()
        self.base_url = base_url.rstrip("/")
        if not self.account_id:
            raise RuntimeError("Cloudflare live controller requires CLOUDFLARE_ACCOUNT_ID")
        if not self.api_token:
            raise RuntimeError("Cloudflare live controller requires CLOUDFLARE_API_TOKEN")

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
            tool_choice: Any = {
                "type": "function",
                "function": {"name": "generate_or_edit"},
            }
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": task.instruction},
            ]
        else:
            if previous_artifact is None or previous_media is None:
                raise ValueError("second decision requires previous_artifact and previous_media")
            tools = [_media_tool(environment, allow_edit=True), _finish_tool()]
            tool_choice = "required"
            encoded = base64.b64encode(previous_media).decode("ascii")
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Original request: {task.instruction}\n"
                                "Review the current image. Either finish, regenerate, or edit once. "
                                f"For edit_previous, previous_artifact_id must be {previous_artifact.artifact_id}. "
                                "For generate, previous_artifact_id must be null."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{previous_artifact.mime_type};base64,{encoded}"
                            },
                        },
                    ],
                },
            ]

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "parallel_tool_calls": False,
            "stream": False,
            "max_completion_tokens": self.config.max_output_tokens or 1024,
            "store": False,
        }
        if self.config.reasoning_effort:
            payload["reasoning_effort"] = self.config.reasoning_effort

        endpoint = f"{self.base_url}/accounts/{self.account_id}/ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        try:
            response = self.transport.post_json(endpoint, headers, payload)
        except Exception as exc:
            raise ControllerExecutionError(
                f"Cloudflare controller request failed ({type(exc).__name__})"
            ) from exc

        if not isinstance(response, Mapping):
            raise ControllerProtocolError("Cloudflare controller response must be an object")
        choices = response.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], Mapping):
            raise ControllerProtocolError("controller must return exactly one choice")
        message = choices[0].get("message")
        if not isinstance(message, Mapping):
            raise ControllerProtocolError("controller choice is missing assistant message")
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list) or len(tool_calls) != 1 or not isinstance(tool_calls[0], Mapping):
            raise ControllerProtocolError("controller must return exactly one recognized function call")
        call = tool_calls[0]
        function = call.get("function")
        if not isinstance(function, Mapping):
            raise ControllerProtocolError("controller tool call is missing function payload")
        name = str(function.get("name") or "")
        arguments = _parse_arguments(function.get("arguments"))

        observable = (
            {
                "type": "function_call",
                "id": str(call.get("id")) if call.get("id") else None,
                "name": name,
                "arguments": arguments,
            },
        )
        response_id = response.get("id")
        actual_model = response.get("model")

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
                usage=_usage(response),
                observable_output=observable,
            )

        if name != "generate_or_edit":
            raise ControllerProtocolError(f"unknown controller function: {name}")

        required = {
            "backend",
            "prompt",
            "operation",
            "aspect_ratio",
            "quality_tier",
            "previous_artifact_id",
        }
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
            usage=_usage(response),
            observable_output=observable,
        )
