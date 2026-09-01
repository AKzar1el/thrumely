from __future__ import annotations

import base64
from typing import Any, Mapping

from .interfaces import ControllerDecision
from .schema import (
    ControllerConfig,
    MediaArtifact,
    MediaOperation,
    NormalizedMediaRequest,
    TaskSpec,
    ToolEnvironment,
)

SYSTEM_PROMPT = """You are the controller in a neutral generative-media research evaluation.
Your objective is to satisfy the user's visual request using only the benchmark-owned client tools provided.
Do not assume any backend is better than another and do not use provider-specific knowledge that is not present in the tool schema.
You have at most two media calls. The first decision must generate an image. After viewing the first image, either finish or make one final generate/edit call.
Return only one tool decision. Do not provide chain-of-thought or an explanation."""

_ASPECT_RATIOS = ("1:1", "3:2", "2:3", "16:9", "9:16")
_QUALITY_TIERS = ("draft", "standard", "high")


class AnthropicControllerProtocolError(RuntimeError):
    pass


class AnthropicControllerExecutionError(RuntimeError):
    pass


def _media_tool(environment: ToolEnvironment, *, allow_edit: bool) -> dict[str, Any]:
    operations = [MediaOperation.GENERATE.value]
    if allow_edit:
        operations.append(MediaOperation.EDIT_PREVIOUS.value)
    return {
        "name": "generate_or_edit",
        "description": "Create or revise one image through a benchmark-normalized backend.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "backend": {"type": "string", "enum": list(environment.available_backends)},
                "prompt": {"type": "string"},
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
        "name": "finish",
        "description": "Accept the current image as the final output and stop.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    }


def _usage_dict(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json", exclude_none=True)
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "__dict__"):
        return {
            str(key): item
            for key, item in vars(value).items()
            if not str(key).startswith("_") and isinstance(item, (str, int, float, bool, type(None)))
        }
    return {}


def _observable_tool_uses(content: Any) -> tuple[Mapping[str, Any], ...]:
    output: list[Mapping[str, Any]] = []
    for block in content or []:
        if getattr(block, "type", None) != "tool_use":
            continue
        tool_input = getattr(block, "input", None)
        output.append(
            {
                "type": "tool_use",
                "id": str(getattr(block, "id", "")),
                "name": str(getattr(block, "name", "")),
                "input": dict(tool_input) if isinstance(tool_input, Mapping) else {},
            }
        )
    return tuple(output)


class AnthropicController:
    def __init__(self, config: ControllerConfig, client: Any | None = None) -> None:
        if config.provider != "anthropic":
            raise ValueError("AnthropicController requires provider='anthropic'")
        self.config = config
        if client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise RuntimeError("Anthropic live adapter requires the 'anthropic' optional dependency") from exc
            client = anthropic.Anthropic()
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
            messages: list[dict[str, Any]] = [{"role": "user", "content": task.instruction}]
        else:
            if previous_artifact is None or previous_media is None:
                raise ValueError("second decision requires previous_artifact and previous_media")
            tools = [_media_tool(environment, allow_edit=True), _finish_tool()]
            encoded = base64.b64encode(previous_media).decode("ascii")
            messages = [
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
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": previous_artifact.mime_type,
                                "data": encoded,
                            },
                        },
                    ],
                }
            ]

        try:
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_output_tokens or 1024,
                system=SYSTEM_PROMPT,
                tools=tools,
                tool_choice={"type": "any", "disable_parallel_tool_use": True},
                messages=messages,
            )
        except Exception as exc:
            raise AnthropicControllerExecutionError(
                f"Anthropic controller request failed ({type(exc).__name__})"
            ) from exc

        tool_uses = [block for block in (getattr(response, "content", None) or []) if getattr(block, "type", None) == "tool_use"]
        if len(tool_uses) != 1:
            raise AnthropicControllerProtocolError("controller must return exactly one tool_use block")

        block = tool_uses[0]
        name = str(getattr(block, "name", ""))
        arguments = getattr(block, "input", None)
        if not isinstance(arguments, Mapping):
            raise AnthropicControllerProtocolError("controller tool input must be an object")
        arguments = dict(arguments)

        response_id = getattr(response, "id", None)
        actual_model = getattr(response, "model", None)
        usage = _usage_dict(getattr(response, "usage", None))
        observable = _observable_tool_uses(getattr(response, "content", None))

        if name == "finish":
            if call_index == 1:
                raise AnthropicControllerProtocolError("finish is not allowed before the first media call")
            if arguments:
                raise AnthropicControllerProtocolError("finish does not accept arguments")
            return ControllerDecision(
                action="finish",
                request=None,
                response_id=str(response_id) if response_id else None,
                actual_model=str(actual_model) if actual_model else None,
                usage=usage,
                observable_output=observable,
            )

        if name != "generate_or_edit":
            raise AnthropicControllerProtocolError(f"unknown controller tool: {name}")

        required = {"backend", "prompt", "operation", "aspect_ratio", "quality_tier", "previous_artifact_id"}
        if set(arguments) != required:
            raise AnthropicControllerProtocolError("generate_or_edit input does not match benchmark schema")
        if arguments["aspect_ratio"] not in _ASPECT_RATIOS:
            raise AnthropicControllerProtocolError("controller returned unsupported aspect ratio")
        if arguments["quality_tier"] not in _QUALITY_TIERS:
            raise AnthropicControllerProtocolError("controller returned unsupported quality tier")
        try:
            operation = MediaOperation(arguments["operation"])
        except ValueError as exc:
            raise AnthropicControllerProtocolError("controller returned unsupported media operation") from exc
        if call_index == 1 and operation is not MediaOperation.GENERATE:
            raise AnthropicControllerProtocolError("first media decision must use generate")
        if operation is MediaOperation.EDIT_PREVIOUS:
            if previous_artifact is None or arguments["previous_artifact_id"] != previous_artifact.artifact_id:
                raise AnthropicControllerProtocolError("edit_previous must reference the current artifact exactly")
        elif arguments["previous_artifact_id"] is not None:
            raise AnthropicControllerProtocolError("generate must set previous_artifact_id to null")

        try:
            normalized = NormalizedMediaRequest(
                backend=str(arguments["backend"]),
                prompt=str(arguments["prompt"]),
                operation=operation,
                aspect_ratio=str(arguments["aspect_ratio"]),
                quality_tier=str(arguments["quality_tier"]),
                previous_artifact_id=arguments["previous_artifact_id"],
                environment=environment,
            )
        except (TypeError, ValueError) as exc:
            raise AnthropicControllerProtocolError(f"invalid normalized media request: {exc}") from exc

        return ControllerDecision(
            action="media",
            request=normalized,
            response_id=str(response_id) if response_id else None,
            actual_model=str(actual_model) if actual_model else None,
            usage=usage,
            observable_output=observable,
        )
