from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime
from urllib.parse import urlparse

from .freeze_bundle import FreezeReadyBundle, compute_freeze_bundle_sha256
from .hashing import content_hash

EXPECTED_FAMILIES = (
    "compositional constraints",
    "typography and layout",
    "styled visual brief",
    "product/editorial scene",
    "revision-sensitive multi-constraint brief",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


@dataclass(frozen=True)
class PreflightCheck:
    check_id: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class FreezePreflightReport:
    status: str
    production_launch_allowed: bool
    bundle_sha256: str
    plan_sha256: str
    checks: tuple[PreflightCheck, ...]
    failed_check_ids: tuple[str, ...]
    report_sha256: str


def _check(check_id: str, condition: bool, detail: str) -> PreflightCheck:
    return PreflightCheck(check_id=check_id, passed=bool(condition), detail=detail)


def _is_utc_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0


def _is_iso_date(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _report_payload(report: FreezePreflightReport) -> dict[str, object]:
    return {
        "status": report.status,
        "production_launch_allowed": report.production_launch_allowed,
        "bundle_sha256": report.bundle_sha256,
        "plan_sha256": report.plan_sha256,
        "checks": report.checks,
        "failed_check_ids": report.failed_check_ids,
    }


def evaluate_freeze_preflight(bundle: FreezeReadyBundle) -> FreezePreflightReport:
    metadata = bundle.metadata
    expected = bundle.expected_outputs
    family_counts = Counter(task.family for task in bundle.tasks)
    expected_family_counts = {family: 20 for family in EXPECTED_FAMILIES}

    backend_verified = (
        len(bundle.backends) == 3
        and all(
            backend.backend_id.strip()
            and backend.provider.strip()
            and backend.model.strip()
            and backend.version_status in {"pinned", "dated", "stable-alias"}
            and _is_iso_date(backend.verified_at)
            and backend.source_urls
            and all(_is_https_url(url) for url in backend.source_urls)
            for backend in bundle.backends
        )
    )

    checks = (
        _check(
            "bundle_integrity",
            compute_freeze_bundle_sha256(replace(bundle, bundle_sha256="")) == bundle.bundle_sha256,
            "bundle content hash matches",
        ),
        _check(
            "prepared_timestamp_utc",
            _is_utc_timestamp(metadata.prepared_at_utc),
            "freeze preparation timestamp is explicit UTC",
        ),
        _check(
            "commit_pinned",
            bool(_COMMIT_RE.fullmatch(metadata.benchmark_commit_sha)),
            "benchmark commit SHA is present",
        ),
        _check(
            "tagged_code",
            isinstance(metadata.benchmark_tag, str) and bool(metadata.benchmark_tag.strip()),
            "benchmark tag is present",
        ),
        _check(
            "tag_matches_commit",
            bool(_COMMIT_RE.fullmatch(metadata.benchmark_tag_commit_sha))
            and metadata.benchmark_tag_commit_sha == metadata.benchmark_commit_sha,
            "benchmark tag must resolve to the benchmark commit",
        ),
        _check("clean_working_tree", metadata.working_tree_dirty is False, "working tree must be clean"),
        _check(
            "research_spec_hash",
            bool(_SHA256_RE.fullmatch(metadata.research_spec_sha256)),
            "research specification hash is present",
        ),
        _check(
            "analysis_plan_hash",
            bool(_SHA256_RE.fullmatch(metadata.analysis_plan_sha256)),
            "analysis plan hash is present",
        ),
        _check(
            "task_corpus_hash",
            bool(_SHA256_RE.fullmatch(metadata.task_corpus_sha256)),
            "task corpus hash is present",
        ),
        _check(
            "provider_inventory_hash",
            bool(_SHA256_RE.fullmatch(metadata.provider_inventory_sha256)),
            "provider inventory hash is present",
        ),
        _check(
            "tool_schema_hash",
            bool(_SHA256_RE.fullmatch(metadata.normalized_tool_schema_sha256)),
            "normalized tool schema hash is present",
        ),
        _check(
            "frozen_task_corpus",
            metadata.task_corpus_status == "frozen-v1",
            "task corpus status must be frozen-v1",
        ),
        _check(
            "frozen_configuration",
            metadata.configuration_status == "frozen-v1",
            "configuration status must be frozen-v1",
        ),
        _check(
            "frozen_analysis_plan",
            metadata.analysis_plan_status == "frozen-v1",
            "analysis plan status must be frozen-v1",
        ),
        _check(
            "not_synthetic_fixture",
            metadata.synthetic_fixture is False,
            "synthetic fixtures can never authorize production",
        ),
        _check(
            "production_classification",
            bundle.plan.data_classification == "frozen-v1-production",
            "plan classification must be frozen-v1-production",
        ),
        _check("task_count", len(bundle.tasks) == 100, "production corpus must contain exactly 100 tasks"),
        _check(
            "task_family_balance",
            family_counts == expected_family_counts,
            "production corpus must contain exactly 20 tasks in each planned family",
        ),
        _check(
            "controller_count",
            len(bundle.plan.controller_ids) == 2,
            "production plan must contain exactly two controllers",
        ),
        _check(
            "environment_count",
            len(bundle.plan.environment_ids) == 4,
            "production plan must contain exactly four tool environments",
        ),
        _check(
            "replication_count",
            bundle.plan.replications == 2,
            "production plan must use exactly two stochastic replications",
        ),
        _check(
            "trajectory_inventory",
            expected.trajectory_count == 1600 and len(bundle.plan.cells) == 1600,
            "production plan must contain exactly 1600 trajectory cells",
        ),
        _check(
            "media_call_inventory",
            expected.max_media_call_count == 3200,
            "maximum media-call inventory must equal 3200",
        ),
        _check("rating_inventory", expected.rating_item_count == 1600, "rating inventory must equal 1600"),
        _check(
            "pairwise_inventory",
            expected.chooser_vs_fixed_pair_count == 1200
            and expected.cross_controller_chooser_pair_count == 200
            and expected.pairwise_item_count == 1400,
            "pairwise inventory must equal 1200 chooser-vs-fixed plus 200 cross-controller chooser",
        ),
        _check(
            "base_human_response_inventory",
            expected.responses_per_rating_item == 5
            and expected.responses_per_pairwise_item == 5
            and expected.base_human_response_count == 15000,
            "base human-response inventory must equal 15000",
        ),
        _check(
            "backend_inventory_verified",
            backend_verified,
            "all three backend snapshots require provider/model/version status, ISO verification date, and valid HTTPS source URLs",
        ),
    )
    failed = tuple(check.check_id for check in checks if not check.passed)
    status = "PASS" if not failed else "BLOCKED"
    provisional = FreezePreflightReport(
        status=status,
        production_launch_allowed=status == "PASS",
        bundle_sha256=bundle.bundle_sha256,
        plan_sha256=bundle.plan.plan_sha256,
        checks=checks,
        failed_check_ids=failed,
        report_sha256="",
    )
    return replace(provisional, report_sha256=content_hash(_report_payload(provisional)))


def require_production_launch_allowed(report: FreezePreflightReport) -> None:
    if report.status != "PASS" or not report.production_launch_allowed:
        failed = ", ".join(report.failed_check_ids) or "unknown preflight failure"
        raise RuntimeError(f"production launch blocked: {failed}")


def _write_json(path, value) -> None:
    import json

    from .serialization import to_primitive

    path.write_text(json.dumps(to_primitive(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path, values) -> None:
    import json

    from .serialization import to_primitive

    with path.open("w", encoding="utf-8") as handle:
        for value in values:
            handle.write(json.dumps(to_primitive(value), sort_keys=True) + "\n")


def write_freeze_preflight_bundle(output_dir, bundle: FreezeReadyBundle, report: FreezePreflightReport):
    import hashlib
    from pathlib import Path

    root = Path(output_dir)
    if report.bundle_sha256 != bundle.bundle_sha256 or report.plan_sha256 != bundle.plan.plan_sha256:
        raise ValueError("report does not belong to bundle")
    root.mkdir(parents=True, exist_ok=False)

    _write_json(root / "freeze-metadata.json", bundle.metadata)
    _write_json(root / "experiment-plan.json", bundle.plan)
    _write_jsonl(root / "cells.jsonl", bundle.plan.cells)
    _write_jsonl(root / "tasks.jsonl", bundle.tasks)
    _write_json(
        root / "configuration.json",
        {
            "controllers": bundle.controllers,
            "environments": bundle.environments,
            "backends": bundle.backends,
        },
    )
    _write_json(root / "expected-outputs.json", bundle.expected_outputs)
    _write_json(root / "preflight.json", report)

    component_files = (
        "freeze-metadata.json",
        "experiment-plan.json",
        "cells.jsonl",
        "tasks.jsonl",
        "configuration.json",
        "expected-outputs.json",
        "preflight.json",
    )
    file_hashes = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in component_files
    }
    _write_json(
        root / "bundle-manifest.json",
        {
            "bundle_schema_version": bundle.bundle_schema_version,
            "bundle_sha256": bundle.bundle_sha256,
            "plan_sha256": bundle.plan.plan_sha256,
            "files": file_hashes,
        },
    )
    return root


def build_synthetic_freeze_preflight():
    from .experiment_plan import compile_experiment_plan
    from .freeze_bundle import BackendConfigSnapshot, FreezeMetadata, compile_freeze_bundle
    from .schema import ControllerConfig, TaskSpec, ToolEnvironment

    tasks = tuple(
        TaskSpec(
            task_id=f"synthetic-{family_index}-{item_index:02d}",
            family=family,
            instruction=f"Synthetic freeze-preflight instruction {family_index}-{item_index}",
        )
        for family_index, family in enumerate(EXPECTED_FAMILIES)
        for item_index in range(20)
    )
    controllers = (
        ControllerConfig("synthetic-controller-a", "synthetic", "controller-model-a", sdk_version="0"),
        ControllerConfig("synthetic-controller-b", "synthetic", "controller-model-b", sdk_version="0"),
    )
    environments = (
        ToolEnvironment("synthetic-fixed-a", "fixed", ("synthetic-backend-a",), 2),
        ToolEnvironment("synthetic-fixed-b", "fixed", ("synthetic-backend-b",), 2),
        ToolEnvironment("synthetic-fixed-c", "fixed", ("synthetic-backend-c",), 2),
        ToolEnvironment(
            "synthetic-chooser",
            "chooser",
            ("synthetic-backend-a", "synthetic-backend-b", "synthetic-backend-c"),
            2,
        ),
    )
    backends = tuple(
        BackendConfigSnapshot(
            backend_id=f"synthetic-backend-{letter}",
            provider="synthetic",
            model=f"synthetic-image-model-{letter}",
            version_status="pinned",
            verified_at="2026-09-01",
            source_urls=(f"https://example.invalid/{letter}",),
        )
        for letter in ("a", "b", "c")
    )
    plan = compile_experiment_plan(
        tasks,
        controllers,
        environments,
        replications=2,
        data_classification="frozen-v1-production",
    )
    metadata = FreezeMetadata(
        prepared_at_utc="2026-09-01T00:00:00+00:00",
        benchmark_commit_sha="0" * 40,
        benchmark_tag="synthetic-v1-freeze",
        benchmark_tag_commit_sha="0" * 40,
        working_tree_dirty=False,
        research_spec_sha256="1" * 64,
        analysis_plan_sha256="2" * 64,
        task_corpus_sha256="3" * 64,
        provider_inventory_sha256="4" * 64,
        normalized_tool_schema_sha256="5" * 64,
        task_corpus_status="frozen-v1",
        configuration_status="frozen-v1",
        analysis_plan_status="frozen-v1",
        synthetic_fixture=True,
    )
    bundle = compile_freeze_bundle(plan, tasks, controllers, environments, backends, metadata)
    report = evaluate_freeze_preflight(bundle)
    summary = {
        "mode": "SYNTHETIC_FREEZE_PREFLIGHT_ONLY",
        "status": report.status,
        "production_launch_allowed": report.production_launch_allowed,
        "failed_check_ids": report.failed_check_ids,
        "bundle_sha256": bundle.bundle_sha256,
        "plan_sha256": bundle.plan.plan_sha256,
        "tasks": len(bundle.tasks),
        "trajectory_cells": bundle.expected_outputs.trajectory_count,
        "rating_items": bundle.expected_outputs.rating_item_count,
        "pairwise_items": bundle.expected_outputs.pairwise_item_count,
        "base_human_responses": bundle.expected_outputs.base_human_response_count,
        "network_calls": 0,
        "hosted_calls": 0,
        "datapoint_jobs": 0,
        "credits_spent": 0,
    }
    return bundle, report, summary


def main() -> None:
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Validate Thrumely's zero-cost freeze-ready production gate")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.synthetic:
        raise SystemExit("Only --synthetic is enabled before real production freeze inputs exist")

    bundle, report, summary = build_synthetic_freeze_preflight()
    if args.output is not None:
        write_freeze_preflight_bundle(args.output, bundle, report)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if report.status != "BLOCKED" or report.failed_check_ids != ("not_synthetic_fixture",):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
