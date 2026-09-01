from __future__ import annotations

from dataclasses import replace

import pytest

from thrumely.experiment_plan import compile_experiment_plan
from thrumely.freeze_bundle import BackendConfigSnapshot, FreezeMetadata, compile_freeze_bundle
from thrumely.freeze_preflight import evaluate_freeze_preflight, require_production_launch_allowed
from thrumely.schema import ControllerConfig, TaskSpec, ToolEnvironment

FAMILIES = (
    "compositional constraints",
    "typography and layout",
    "styled visual brief",
    "product/editorial scene",
    "revision-sensitive multi-constraint brief",
)


def tasks_100():
    rows = []
    for family_index, family in enumerate(FAMILIES):
        for item_index in range(20):
            rows.append(
                TaskSpec(
                    task_id=f"task-{family_index}-{item_index:02d}",
                    family=family,
                    instruction=f"Synthetic instruction {family_index}-{item_index}",
                )
            )
    return tuple(rows)


def controllers():
    return (
        ControllerConfig("controller-a", "provider-a", "model-a", sdk_version="1.0"),
        ControllerConfig("controller-b", "provider-b", "model-b", sdk_version="2.0"),
    )


def environments():
    return (
        ToolEnvironment("fixed-a", "fixed", ("backend-a",), 2),
        ToolEnvironment("fixed-b", "fixed", ("backend-b",), 2),
        ToolEnvironment("fixed-c", "fixed", ("backend-c",), 2),
        ToolEnvironment("chooser", "chooser", ("backend-a", "backend-b", "backend-c"), 2),
    )


def backends():
    return (
        BackendConfigSnapshot(
            "backend-a",
            "image-provider-a",
            "image-model-a",
            "pinned",
            "2026-09-01",
            ("https://example.com/a",),
        ),
        BackendConfigSnapshot(
            "backend-b",
            "image-provider-b",
            "image-model-b",
            "stable-alias",
            "2026-09-01",
            ("https://example.com/b",),
        ),
        BackendConfigSnapshot(
            "backend-c",
            "image-provider-c",
            "image-model-c",
            "pinned",
            "2026-09-01",
            ("https://example.com/c",),
        ),
    )


def metadata(*, synthetic_fixture=False):
    return FreezeMetadata(
        prepared_at_utc="2026-09-01T19:00:00+00:00",
        benchmark_commit_sha="f" * 40,
        benchmark_tag="v1.0.0-freeze",
        benchmark_tag_commit_sha="f" * 40,
        working_tree_dirty=False,
        research_spec_sha256="a" * 64,
        analysis_plan_sha256="b" * 64,
        task_corpus_sha256="c" * 64,
        provider_inventory_sha256="d" * 64,
        normalized_tool_schema_sha256="e" * 64,
        task_corpus_status="frozen-v1",
        configuration_status="frozen-v1",
        analysis_plan_status="frozen-v1",
        synthetic_fixture=synthetic_fixture,
    )


def build_bundle(*, synthetic_fixture=False, tasks=None, ctrls=None, envs=None, backend_rows=None):
    task_rows = tasks or tasks_100()
    controller_rows = ctrls or controllers()
    environment_rows = envs or environments()
    plan = compile_experiment_plan(
        task_rows,
        controller_rows,
        environment_rows,
        replications=2,
        data_classification="frozen-v1-production",
    )
    return compile_freeze_bundle(
        plan,
        task_rows,
        controller_rows,
        environment_rows,
        backend_rows or backends(),
        metadata(synthetic_fixture=synthetic_fixture),
    )


def test_complete_v1_bundle_has_exact_inventory_and_passes_preflight():
    bundle = build_bundle()
    assert bundle.expected_outputs.trajectory_count == 1600
    assert bundle.expected_outputs.final_output_count == 1600
    assert bundle.expected_outputs.max_media_call_count == 3200
    assert bundle.expected_outputs.rating_item_count == 1600
    assert bundle.expected_outputs.chooser_vs_fixed_pair_count == 1200
    assert bundle.expected_outputs.cross_controller_chooser_pair_count == 200
    assert bundle.expected_outputs.pairwise_item_count == 1400
    assert bundle.expected_outputs.base_human_response_count == 15000

    report = evaluate_freeze_preflight(bundle)
    assert report.status == "PASS"
    assert report.production_launch_allowed is True
    assert report.failed_check_ids == ()
    require_production_launch_allowed(report)


def test_bundle_hash_is_deterministic_and_input_order_independent():
    tasks = tasks_100()
    ctrls = controllers()
    envs = environments()
    a = build_bundle(tasks=tasks, ctrls=ctrls, envs=envs, backend_rows=backends())

    plan_b = compile_experiment_plan(
        tuple(reversed(tasks)),
        tuple(reversed(ctrls)),
        tuple(reversed(envs)),
        replications=2,
        data_classification="frozen-v1-production",
    )
    b = compile_freeze_bundle(
        plan_b,
        tuple(reversed(tasks)),
        tuple(reversed(ctrls)),
        tuple(reversed(envs)),
        tuple(reversed(backends())),
        metadata(),
    )
    assert a.bundle_sha256 == b.bundle_sha256
    assert a.plan.plan_sha256 == b.plan.plan_sha256


def test_compile_rejects_configuration_that_does_not_match_plan():
    tasks = tasks_100()
    ctrls = controllers()
    envs = environments()
    plan = compile_experiment_plan(
        tasks,
        ctrls,
        envs,
        replications=2,
        data_classification="frozen-v1-production",
    )
    changed = (replace(ctrls[0], model="changed-model"), ctrls[1])
    with pytest.raises(ValueError, match="configuration does not match experiment plan"):
        compile_freeze_bundle(plan, tasks, changed, envs, backends(), metadata())


def test_compile_rejects_missing_or_extra_backend_snapshots():
    tasks = tasks_100()
    ctrls = controllers()
    envs = environments()
    plan = compile_experiment_plan(
        tasks,
        ctrls,
        envs,
        replications=2,
        data_classification="frozen-v1-production",
    )
    with pytest.raises(ValueError, match="backend snapshot IDs must exactly match"):
        compile_freeze_bundle(plan, tasks, ctrls, envs, backends()[:2], metadata())


def test_preflight_blocks_unfrozen_dirty_untagged_and_synthetic_states():
    bundle = build_bundle()
    blocked = replace(
        bundle,
        metadata=replace(
            bundle.metadata,
            benchmark_tag="",
            working_tree_dirty=True,
            task_corpus_status="candidate",
            configuration_status="calibration-candidate",
            analysis_plan_status="draft",
            synthetic_fixture=True,
        ),
    )
    report = evaluate_freeze_preflight(blocked)
    assert report.status == "BLOCKED"
    assert report.production_launch_allowed is False
    assert {
        "tagged_code",
        "clean_working_tree",
        "frozen_task_corpus",
        "frozen_configuration",
        "frozen_analysis_plan",
        "not_synthetic_fixture",
    }.issubset(set(report.failed_check_ids))
    with pytest.raises(RuntimeError, match="production launch blocked"):
        require_production_launch_allowed(report)


def test_preflight_blocks_wrong_task_balance_even_if_count_is_100():
    rows = list(tasks_100())
    rows[0] = replace(rows[0], family=FAMILIES[1])
    bundle = build_bundle(tasks=tuple(rows))
    report = evaluate_freeze_preflight(bundle)
    assert report.status == "BLOCKED"
    assert "task_family_balance" in report.failed_check_ids


def test_preflight_blocks_unverified_backend_inventory():
    rows = list(backends())
    rows[0] = replace(rows[0], verified_at="", source_urls=())
    bundle = build_bundle(backend_rows=tuple(rows))
    report = evaluate_freeze_preflight(bundle)
    assert report.status == "BLOCKED"
    assert "backend_inventory_verified" in report.failed_check_ids


def test_preflight_report_hash_is_deterministic():
    bundle = build_bundle()
    assert evaluate_freeze_preflight(bundle).report_sha256 == evaluate_freeze_preflight(bundle).report_sha256


def test_synthetic_preflight_is_structurally_ready_but_never_launch_authorized(tmp_path):
    from thrumely.freeze_preflight import build_synthetic_freeze_preflight, write_freeze_preflight_bundle

    bundle, report, summary = build_synthetic_freeze_preflight()
    assert report.status == "BLOCKED"
    assert report.production_launch_allowed is False
    assert report.failed_check_ids == ("not_synthetic_fixture",)
    assert summary["mode"] == "SYNTHETIC_FREEZE_PREFLIGHT_ONLY"
    assert summary["network_calls"] == 0
    assert summary["hosted_calls"] == 0
    assert summary["datapoint_jobs"] == 0
    assert summary["credits_spent"] == 0
    assert summary["trajectory_cells"] == 1600
    assert summary["rating_items"] == 1600
    assert summary["pairwise_items"] == 1400

    output = write_freeze_preflight_bundle(tmp_path / "freeze", bundle, report)
    assert output == tmp_path / "freeze"
    assert (output / "freeze-metadata.json").exists()
    assert (output / "experiment-plan.json").exists()
    assert (output / "cells.jsonl").exists()
    assert (output / "tasks.jsonl").exists()
    assert (output / "configuration.json").exists()
    assert (output / "expected-outputs.json").exists()
    assert (output / "preflight.json").exists()
    assert (output / "bundle-manifest.json").exists()

    import hashlib
    import json

    manifest = json.loads((output / "bundle-manifest.json").read_text())
    assert manifest["bundle_sha256"] == bundle.bundle_sha256
    assert manifest["plan_sha256"] == bundle.plan.plan_sha256
    for relative_path, expected_sha in manifest["files"].items():
        actual = hashlib.sha256((output / relative_path).read_bytes()).hexdigest()
        assert actual == expected_sha


def test_writer_refuses_mismatched_report(tmp_path):
    from thrumely.freeze_preflight import write_freeze_preflight_bundle

    bundle = build_bundle()
    other = build_bundle(synthetic_fixture=True)
    report = evaluate_freeze_preflight(other)
    with pytest.raises(ValueError, match="report does not belong to bundle"):
        write_freeze_preflight_bundle(tmp_path / "bad", bundle, report)


def test_preflight_blocks_tag_that_does_not_point_to_commit():
    bundle = build_bundle()
    tampered = replace(
        bundle,
        metadata=replace(bundle.metadata, benchmark_tag_commit_sha="e" * 40),
    )
    report = evaluate_freeze_preflight(tampered)
    assert report.status == "BLOCKED"
    assert "tag_matches_commit" in report.failed_check_ids
