from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import thrumely.calibration as calibration


PROFILE = "gpt54-mini-diagnostic"
MODEL = "openai/gpt-5.4-mini"
WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "vercel-gpt54-mini-diagnostic.yml"


def test_vercel_diagnostic_profile_selects_gpt54_mini_and_cannot_count_as_sol_gate1(
    tmp_path: Path,
    monkeypatch,
) -> None:
    balances = iter(
        [
            {"balance": "5.00", "total_used": "0.00"},
            {"balance": "4.99", "total_used": "0.01"},
        ]
    )
    monkeypatch.setattr(calibration, "fetch_vercel_gateway_credits", lambda api_key: next(balances))
    monkeypatch.setattr(calibration, "_openai_sdk_version", lambda: "3.6.0")

    constructed: list[dict] = []

    class FakeOpenAI:
        def __new__(cls, **kwargs):
            constructed.append(kwargs)
            return SimpleNamespace()

    module = ModuleType("openai")
    module.OpenAI = FakeOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", module)

    captured: dict[str, object] = {}
    run_dir = tmp_path / "run"

    def fake_run_calibration(output, tasks, controller, provider, **kwargs):
        captured["controller"] = controller
        captured["provider"] = provider
        captured["transport"] = dict(kwargs["transport_metadata"])
        return run_dir

    def fake_update_transport_metadata(path, transport):
        captured["final_transport"] = dict(transport)

    monkeypatch.setattr(calibration, "run_calibration", fake_run_calibration)
    monkeypatch.setattr(calibration, "_update_transport_metadata", fake_update_transport_metadata)

    args = SimpleNamespace(
        output=tmp_path / "results",
        tasks=tmp_path / "tasks.json",
        task_id="cal-openai-001",
        replication=1,
        vercel_controller_profile=PROFILE,
    )

    result = calibration._run_vercel_gateway(args, "gateway-secret")

    assert result == run_dir
    assert constructed == [
        {
            "api_key": "gateway-secret",
            "base_url": "https://ai-gateway.vercel.sh/v1",
            "max_retries": 0,
        }
    ]
    controller = captured["controller"]
    assert controller.config.model == MODEL
    assert controller.config.controller_id == "openai-gpt54-mini-vercel-diagnostic"
    transport = captured["final_transport"]
    assert transport["controller_profile"] == PROFILE
    assert transport["controller_gateway_model"] == MODEL
    assert transport["intended_gate1_controller_model"] == "openai/gpt-5.6-sol"
    assert transport["diagnostic_only"] is True
    assert transport["counts_as_sol_gate1_evidence"] is False
    assert transport["provider_fallback_allowed"] is False
    assert transport["model_fallback_allowed"] is False


def test_cli_dry_run_labels_gpt54_mini_as_diagnostic_only(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    task_path = tmp_path / "tasks.json"
    task_path.write_text(
        json.dumps(
            {
                "calibration_only": True,
                "tasks": [
                    {
                        "task_id": "cal-openai-001",
                        "family": "compositional-constraints",
                        "instruction": "Create a blue square.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "thrumely.calibration",
            "--tasks",
            str(task_path),
            "--task-id",
            "cal-openai-001",
            "--transport",
            "vercel-gateway",
            "--vercel-controller-profile",
            PROFILE,
        ],
    )

    calibration.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "DRY_RUN_ONLY"
    assert payload["controller_profile"] == PROFILE
    assert payload["controller_model"] == MODEL
    assert payload["diagnostic_only"] is True
    assert payload["counts_as_sol_gate1_evidence"] is False


def test_gpt54_mini_diagnostic_workflow_is_separate_manual_and_bounded() -> None:
    assert WORKFLOW.exists()
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text
    assert "\n  push:" not in text
    assert "\n  pull_request:" not in text
    assert "RUN_GPT54_MINI_DIAGNOSTIC" in text
    assert "RUN_CAL_OPENAI_001" not in text
    assert "AI_GATEWAY_API_KEY: ${{ secrets.AI_GATEWAY_API_KEY }}" in text
    assert "OPENAI_API_KEY" not in text
    assert text.count("--task-id cal-openai-001") == 1
    assert text.count("--transport vercel-gateway") == 1
    assert text.count("--vercel-controller-profile gpt54-mini-diagnostic") == 1
    assert text.count("--execute-live") == 1
    assert "permissions:\n  contents: read" in text
    assert "cancel-in-progress: false" in text
    assert "if: always()" in text
    assert "path: results/calibration" in text
