from __future__ import annotations

from thrumely.experiment_synthetic import build_synthetic_report


def test_synthetic_experiment_report_is_zero_cost_and_deterministic():
    first = build_synthetic_report()
    second = build_synthetic_report()
    assert first == second
    assert first["mode"] == "SYNTHETIC_EXPERIMENT_PLAN_ONLY"
    assert first["network_calls"] == 0
    assert first["hosted_calls"] == 0
    assert first["datapoint_jobs"] == 0
    assert first["credits_spent"] == 0
    assert first["tasks"] == 3
    assert first["controllers"] == 2
    assert first["environments"] == 4
    assert first["replications"] == 2
    assert first["trajectory_cells"] == 48
    assert first["rating_items"] == 48
    assert first["pairwise_items"] == 42
    assert first["chooser_vs_fixed_items"] == 36
    assert first["cross_controller_chooser_items"] == 6
    assert len(first["plan_sha256"]) == 64
    assert len(first["manifest_sha256"]) == 64
