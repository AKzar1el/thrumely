from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "vercel-gate1.yml"


def test_vercel_gate1_workflow_is_manual_and_fail_closed() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text
    assert "\n  push:" not in text
    assert "\n  pull_request:" not in text
    assert "authorization:" in text
    assert "RUN_CAL_OPENAI_001" in text
    assert "required: true" in text
    assert "permissions:\n  contents: read" in text
    assert "concurrency:" in text
    assert "cancel-in-progress: false" in text


def test_vercel_gate1_workflow_uses_only_gateway_secret_and_one_task() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "AI_GATEWAY_API_KEY: ${{ secrets.AI_GATEWAY_API_KEY }}" in text
    assert "OPENAI_API_KEY" not in text
    assert text.count("--task-id cal-openai-001") == 1
    assert "cal-openai-002" not in text
    assert "cal-openai-003" not in text
    assert "cal-openai-004" not in text
    assert "cal-openai-005" not in text
    assert text.count("--transport vercel-gateway") == 1
    assert text.count("--execute-live") == 1


def test_vercel_gate1_workflow_preserves_bundle_for_review() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in text
    assert "if: always()" in text
    assert "path: results/calibration" in text
