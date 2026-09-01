from dataclasses import FrozenInstanceError

import pytest

from thrumely.schema import (
    CompletionStatus,
    ControllerConfig,
    MediaArtifact,
    MediaOperation,
    MediaStage,
    NormalizedMediaRequest,
    RunManifest,
    ScorerResult,
    TaskSpec,
    ToolCallRecord,
    ToolEnvironment,
    TrajectoryRecord,
)


def test_task_requires_nonempty_instruction() -> None:
    with pytest.raises(ValueError, match="instruction"):
        TaskSpec(task_id="task-001", family="composition", instruction="")


def test_tool_environment_requires_available_backends() -> None:
    with pytest.raises(ValueError, match="backend"):
        ToolEnvironment(environment_id="chooser", mode="chooser", available_backends=())


def test_fixed_environment_requires_exactly_one_backend() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        ToolEnvironment(environment_id="fixed", mode="fixed", available_backends=("a", "b"))


def test_normalized_request_rejects_backend_outside_environment() -> None:
    environment = ToolEnvironment(
        environment_id="fixed-a",
        mode="fixed",
        available_backends=("provider-a",),
    )
    with pytest.raises(ValueError, match="available"):
        NormalizedMediaRequest(
            backend="provider-b",
            prompt="draw a blue square",
            operation=MediaOperation.GENERATE,
            aspect_ratio="1:1",
            quality_tier="standard",
            previous_artifact_id=None,
            environment=environment,
        )


def test_edit_request_requires_previous_artifact() -> None:
    environment = ToolEnvironment("chooser", "chooser", ("a", "b"))
    with pytest.raises(ValueError, match="previous_artifact_id"):
        NormalizedMediaRequest(
            backend="a",
            prompt="revise it",
            operation=MediaOperation.EDIT_PREVIOUS,
            aspect_ratio="1:1",
            quality_tier="standard",
            previous_artifact_id=None,
            environment=environment,
        )


def test_schema_records_are_immutable() -> None:
    controller = ControllerConfig(controller_id="mock-a", provider="mock", model="mock-v1")
    with pytest.raises(FrozenInstanceError):
        controller.model = "changed"  # type: ignore[misc]


def test_complete_record_graph_can_be_constructed() -> None:
    environment = ToolEnvironment("fixed-a", "fixed", ("mock-a",))
    request = NormalizedMediaRequest(
        backend="mock-a",
        prompt="blue square",
        operation=MediaOperation.GENERATE,
        aspect_ratio="1:1",
        quality_tier="standard",
        previous_artifact_id=None,
        environment=environment,
    )
    sha = "a" * 64
    artifact = MediaArtifact(
        artifact_id=f"media:{sha}",
        sha256=sha,
        mime_type="image/svg+xml",
        width=1024,
        height=1024,
        byte_length=12,
        stage=MediaStage.FINAL,
        relative_path=f"media/{sha}.svg",
    )
    call = ToolCallRecord(
        call_index=1,
        request=request,
        raw_request={"prompt": "blue square"},
        raw_response={"request_id": "mock-1"},
        request_id="mock-1",
        artifact_id=artifact.artifact_id,
        latency_seconds=0.0,
        cost_usd=0.0,
        error=None,
        moderation_status=None,
    )
    trajectory = TrajectoryRecord(
        trajectory_id="traj-001",
        task_id="task-001",
        controller_id="controller-a",
        environment_id="fixed-a",
        replication=1,
        tool_calls=(call,),
        final_artifact_id=artifact.artifact_id,
        completion_status=CompletionStatus.SUCCESS,
        infrastructure_error=None,
        messages=(),
        events=(),
    )
    score = ScorerResult(
        score_id="score-001",
        task_id="task-001",
        trajectory_id=trajectory.trajectory_id,
        scorer_name="mock_artifact_present",
        scorer_version="1",
        value=1.0,
        metadata={},
    )
    manifest = RunManifest(
        run_id="run-001",
        timestamp_utc="2026-09-01T00:00:00+00:00",
        package_version="0.1.0",
        python_version="3.11.0",
        benchmark_commit_sha=None,
        working_tree_dirty=None,
        research_spec_sha256=sha,
        requested_trajectories=2,
        completed_trajectories=2,
        media_call_budget=2,
        controller_ids=("controller-a",),
        environment_ids=("fixed-a", "chooser"),
        data_classification="synthetic-offline",
    )
    assert score.value == 1.0
    assert manifest.completed_trajectories == 2


def test_media_artifact_rejects_invalid_sha256() -> None:
    with pytest.raises(ValueError, match="sha256"):
        MediaArtifact(
            artifact_id="media:bad",
            sha256="bad",
            mime_type="image/svg+xml",
            width=1,
            height=1,
            byte_length=1,
            stage=MediaStage.FINAL,
            relative_path="media/bad.svg",
        )
