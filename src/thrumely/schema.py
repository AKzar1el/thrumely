from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _require_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


class CompletionStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    REJECTED = "rejected"


class MediaStage(str, Enum):
    FIRST = "first"
    REVISION = "revision"
    FINAL = "final"


class MediaOperation(str, Enum):
    GENERATE = "generate"
    EDIT_PREVIOUS = "edit_previous"


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    family: str
    instruction: str

    def __post_init__(self) -> None:
        _require_text("task_id", self.task_id)
        _require_text("family", self.family)
        _require_text("instruction", self.instruction)


@dataclass(frozen=True)
class ControllerConfig:
    controller_id: str
    provider: str
    model: str

    def __post_init__(self) -> None:
        _require_text("controller_id", self.controller_id)
        _require_text("provider", self.provider)
        _require_text("model", self.model)


@dataclass(frozen=True)
class ToolEnvironment:
    environment_id: str
    mode: str
    available_backends: tuple[str, ...]
    media_call_budget: int = 2

    def __post_init__(self) -> None:
        _require_text("environment_id", self.environment_id)
        if self.mode not in {"fixed", "chooser"}:
            raise ValueError("mode must be 'fixed' or 'chooser'")
        if not self.available_backends or not all(isinstance(item, str) and item.strip() for item in self.available_backends):
            raise ValueError("available_backends must contain at least one backend")
        if self.mode == "fixed" and len(self.available_backends) != 1:
            raise ValueError("fixed environment requires exactly one backend")
        if self.media_call_budget < 1:
            raise ValueError("media_call_budget must be >= 1")


@dataclass(frozen=True)
class NormalizedMediaRequest:
    backend: str
    prompt: str
    operation: MediaOperation
    aspect_ratio: str
    quality_tier: str
    previous_artifact_id: str | None
    environment: ToolEnvironment

    def __post_init__(self) -> None:
        _require_text("backend", self.backend)
        _require_text("prompt", self.prompt)
        _require_text("aspect_ratio", self.aspect_ratio)
        _require_text("quality_tier", self.quality_tier)
        if self.backend not in self.environment.available_backends:
            raise ValueError("backend must be available in environment")
        if self.operation is MediaOperation.GENERATE and self.previous_artifact_id is not None:
            raise ValueError("generate request must not set previous_artifact_id")
        if self.operation is MediaOperation.EDIT_PREVIOUS and not self.previous_artifact_id:
            raise ValueError("edit_previous request requires previous_artifact_id")


@dataclass(frozen=True)
class ToolCallRecord:
    call_index: int
    request: NormalizedMediaRequest
    raw_request: Mapping[str, Any]
    raw_response: Mapping[str, Any]
    request_id: str | None
    artifact_id: str | None
    latency_seconds: float | None
    cost_usd: float | None
    error: str | None
    moderation_status: str | None

    def __post_init__(self) -> None:
        if self.call_index < 1:
            raise ValueError("call_index must be >= 1")
        if self.latency_seconds is not None and self.latency_seconds < 0:
            raise ValueError("latency_seconds must be >= 0")
        if self.cost_usd is not None and self.cost_usd < 0:
            raise ValueError("cost_usd must be >= 0")


@dataclass(frozen=True)
class MediaArtifact:
    artifact_id: str
    sha256: str
    mime_type: str
    width: int
    height: int
    byte_length: int
    stage: MediaStage
    relative_path: str

    def __post_init__(self) -> None:
        _require_text("artifact_id", self.artifact_id)
        if not _SHA256_RE.fullmatch(self.sha256):
            raise ValueError("sha256 must be a 64-character lowercase hexadecimal digest")
        _require_text("mime_type", self.mime_type)
        _require_text("relative_path", self.relative_path)
        if self.width <= 0 or self.height <= 0:
            raise ValueError("media dimensions must be positive")
        if self.byte_length < 0:
            raise ValueError("byte_length must be >= 0")


@dataclass(frozen=True)
class TrajectoryRecord:
    trajectory_id: str
    task_id: str
    controller_id: str
    environment_id: str
    replication: int
    tool_calls: tuple[ToolCallRecord, ...]
    final_artifact_id: str | None
    completion_status: CompletionStatus
    infrastructure_error: str | None
    messages: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    events: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_text("trajectory_id", self.trajectory_id)
        _require_text("task_id", self.task_id)
        _require_text("controller_id", self.controller_id)
        _require_text("environment_id", self.environment_id)
        if self.replication < 1:
            raise ValueError("replication must be >= 1")
        if self.completion_status is CompletionStatus.SUCCESS and not self.final_artifact_id:
            raise ValueError("successful trajectory requires final_artifact_id")


@dataclass(frozen=True)
class ScorerResult:
    score_id: str
    task_id: str
    trajectory_id: str
    scorer_name: str
    scorer_version: str
    value: float
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        for name, value in (
            ("score_id", self.score_id),
            ("task_id", self.task_id),
            ("trajectory_id", self.trajectory_id),
            ("scorer_name", self.scorer_name),
            ("scorer_version", self.scorer_version),
        ):
            _require_text(name, value)


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    timestamp_utc: str
    package_version: str
    python_version: str
    benchmark_commit_sha: str | None
    working_tree_dirty: bool | None
    research_spec_sha256: str
    requested_trajectories: int
    completed_trajectories: int
    media_call_budget: int
    controller_ids: tuple[str, ...]
    environment_ids: tuple[str, ...]
    data_classification: str

    def __post_init__(self) -> None:
        for name, value in (
            ("run_id", self.run_id),
            ("timestamp_utc", self.timestamp_utc),
            ("package_version", self.package_version),
            ("python_version", self.python_version),
            ("data_classification", self.data_classification),
        ):
            _require_text(name, value)
        if not _SHA256_RE.fullmatch(self.research_spec_sha256):
            raise ValueError("research_spec_sha256 must be a 64-character lowercase hexadecimal digest")
        if self.requested_trajectories < 0 or self.completed_trajectories < 0:
            raise ValueError("trajectory counts must be >= 0")
        if self.completed_trajectories > self.requested_trajectories:
            raise ValueError("completed_trajectories cannot exceed requested_trajectories")
        if self.media_call_budget < 1:
            raise ValueError("media_call_budget must be >= 1")
