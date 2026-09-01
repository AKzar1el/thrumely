from __future__ import annotations

from html import escape
from typing import Any

from .hashing import content_hash
from .schema import (
    ControllerConfig,
    MediaArtifact,
    MediaOperation,
    NormalizedMediaRequest,
    ScorerResult,
    TaskSpec,
    ToolEnvironment,
)


class MockController:
    def __init__(self, config: ControllerConfig) -> None:
        self.config = config

    def decide(
        self,
        task: TaskSpec,
        environment: ToolEnvironment,
        *,
        call_index: int,
        previous_artifact_id: str | None,
    ) -> NormalizedMediaRequest | None:
        if call_index != 1:
            return None
        backend = environment.available_backends[0]
        return NormalizedMediaRequest(
            backend=backend,
            prompt=task.instruction,
            operation=MediaOperation.GENERATE,
            aspect_ratio="1:1",
            quality_tier="standard",
            previous_artifact_id=None,
            environment=environment,
        )


class MockImageProvider:
    def execute(self, request: NormalizedMediaRequest) -> tuple[bytes, dict[str, Any]]:
        request_id = f"mock-{content_hash(request)[:16]}"
        escaped_prompt = escape(request.prompt)
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">'
            '<rect width="1024" height="1024" fill="white"/>'
            '<rect x="362" y="362" width="300" height="300" fill="blue"/>'
            f'<text x="40" y="980" font-size="24">{escaped_prompt}</text>'
            '</svg>'
        ).encode("utf-8")
        return svg, {
            "request_id": request_id,
            "cost_usd": 0.0,
            "latency_seconds": 0.0,
            "mime_type": "image/svg+xml",
            "width": 1024,
            "height": 1024,
            "raw_request": {
                "backend": request.backend,
                "prompt": request.prompt,
                "operation": request.operation.value,
                "aspect_ratio": request.aspect_ratio,
                "quality_tier": request.quality_tier,
            },
            "raw_response": {
                "request_id": request_id,
                "status": "synthetic",
            },
        }


class MockScorer:
    def score(
        self,
        task: TaskSpec,
        *,
        trajectory_id: str,
        artifact: MediaArtifact,
    ) -> ScorerResult:
        return ScorerResult(
            score_id=f"score-{content_hash((task.task_id, trajectory_id, artifact.artifact_id))[:16]}",
            task_id=task.task_id,
            trajectory_id=trajectory_id,
            scorer_name="mock_artifact_present",
            scorer_version="1",
            value=1.0 if artifact.byte_length > 0 else 0.0,
            metadata={"synthetic": True},
        )
