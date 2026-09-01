from thrumely.mock import MockController, MockImageProvider, MockScorer
from thrumely.schema import ControllerConfig, MediaOperation, MediaStage, TaskSpec, ToolEnvironment
from thrumely.artifacts import ArtifactStore


def _controller() -> MockController:
    return MockController(ControllerConfig("mock-controller", "mock", "mock-v1"))


def test_fixed_environment_selects_its_only_backend() -> None:
    request = _controller().decide(
        TaskSpec("task-1", "composition", "draw blue"),
        ToolEnvironment("fixed-b", "fixed", ("mock-b",)),
        call_index=1,
        previous_artifact_id=None,
    )
    assert request is not None
    assert request.backend == "mock-b"
    assert request.operation is MediaOperation.GENERATE


def test_chooser_selects_first_backend_deterministically() -> None:
    request = _controller().decide(
        TaskSpec("task-1", "composition", "draw blue"),
        ToolEnvironment("chooser", "chooser", ("mock-a", "mock-b", "mock-c")),
        call_index=1,
        previous_artifact_id=None,
    )
    assert request is not None
    assert request.backend == "mock-a"


def test_mock_controller_stops_after_first_media_call() -> None:
    request = _controller().decide(
        TaskSpec("task-1", "composition", "draw blue"),
        ToolEnvironment("fixed-a", "fixed", ("mock-a",)),
        call_index=2,
        previous_artifact_id="media:" + "a" * 64,
    )
    assert request is None


def test_provider_is_deterministic_and_escapes_prompt() -> None:
    controller = _controller()
    request = controller.decide(
        TaskSpec("task-1", "composition", "<script>alert(1)</script>"),
        ToolEnvironment("fixed-a", "fixed", ("mock-a",)),
        call_index=1,
        previous_artifact_id=None,
    )
    assert request is not None
    provider = MockImageProvider()
    first_bytes, first_meta = provider.execute(request)
    second_bytes, second_meta = provider.execute(request)
    assert first_bytes == second_bytes
    assert first_meta["request_id"] == second_meta["request_id"]
    assert first_meta["cost_usd"] == 0.0
    assert b"<script>" not in first_bytes
    assert b"&lt;script&gt;" in first_bytes


def test_mock_scorer_never_claims_human_faithfulness(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    artifact = store.put_media(
        b"<svg/>",
        mime_type="image/svg+xml",
        width=1024,
        height=1024,
        stage=MediaStage.FINAL,
    )
    score = MockScorer().score(
        TaskSpec("task-1", "composition", "draw blue"),
        trajectory_id="traj-1",
        artifact=artifact,
    )
    assert score.scorer_name == "mock_artifact_present"
    assert "faith" not in score.scorer_name
    assert score.value == 1.0
