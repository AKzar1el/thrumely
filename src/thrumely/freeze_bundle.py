from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from .experiment_plan import ExperimentPlan, compile_experiment_plan
from .hashing import content_hash
from .schema import ControllerConfig, TaskSpec, ToolEnvironment


@dataclass(frozen=True)
class BackendConfigSnapshot:
    backend_id: str
    provider: str
    model: str
    version_status: str
    verified_at: str
    source_urls: tuple[str, ...]
    sdk_version: str | None = None
    endpoint: str | None = None


@dataclass(frozen=True)
class FreezeMetadata:
    prepared_at_utc: str
    benchmark_commit_sha: str
    benchmark_tag: str
    benchmark_tag_commit_sha: str
    working_tree_dirty: bool
    research_spec_sha256: str
    analysis_plan_sha256: str
    task_corpus_sha256: str
    provider_inventory_sha256: str
    normalized_tool_schema_sha256: str
    task_corpus_status: str
    configuration_status: str
    analysis_plan_status: str
    synthetic_fixture: bool = False


@dataclass(frozen=True)
class ExpectedOutputInventory:
    trajectory_count: int
    final_output_count: int
    max_media_call_count: int
    rating_item_count: int
    chooser_vs_fixed_pair_count: int
    cross_controller_chooser_pair_count: int
    pairwise_item_count: int
    responses_per_rating_item: int
    responses_per_pairwise_item: int
    base_human_response_count: int


@dataclass(frozen=True)
class FreezeReadyBundle:
    bundle_schema_version: str
    metadata: FreezeMetadata
    plan: ExperimentPlan
    tasks: tuple[TaskSpec, ...]
    controllers: tuple[ControllerConfig, ...]
    environments: tuple[ToolEnvironment, ...]
    backends: tuple[BackendConfigSnapshot, ...]
    expected_outputs: ExpectedOutputInventory
    bundle_sha256: str


def _sorted_unique(items: Iterable[object], attr: str, label: str) -> tuple[object, ...]:
    rows = tuple(items)
    seen: set[str] = set()
    for row in rows:
        value = getattr(row, attr)
        if value in seen:
            raise ValueError(f"duplicate {label}: {value}")
        seen.add(value)
    return tuple(sorted(rows, key=lambda row: getattr(row, attr)))


def _bundle_payload(bundle: FreezeReadyBundle) -> dict[str, object]:
    return {
        "bundle_schema_version": bundle.bundle_schema_version,
        "metadata": bundle.metadata,
        "plan": bundle.plan,
        "tasks": bundle.tasks,
        "controllers": bundle.controllers,
        "environments": bundle.environments,
        "backends": bundle.backends,
        "expected_outputs": bundle.expected_outputs,
    }


def compute_freeze_bundle_sha256(bundle: FreezeReadyBundle) -> str:
    return content_hash(_bundle_payload(bundle))


def compile_freeze_bundle(
    plan: ExperimentPlan,
    tasks: Iterable[TaskSpec],
    controllers: Iterable[ControllerConfig],
    environments: Iterable[ToolEnvironment],
    backends: Iterable[BackendConfigSnapshot],
    metadata: FreezeMetadata,
    *,
    responses_per_item: int = 5,
) -> FreezeReadyBundle:
    if not isinstance(responses_per_item, int) or isinstance(responses_per_item, bool) or responses_per_item < 1:
        raise ValueError("responses_per_item must be a positive integer")

    task_rows = _sorted_unique(tasks, "task_id", "task_id")
    controller_rows = _sorted_unique(controllers, "controller_id", "controller_id")
    environment_rows = _sorted_unique(environments, "environment_id", "environment_id")
    backend_rows = _sorted_unique(backends, "backend_id", "backend_id")

    rebuilt = compile_experiment_plan(
        task_rows,
        controller_rows,
        environment_rows,
        replications=plan.replications,
        data_classification=plan.data_classification,
    )
    if rebuilt.plan_sha256 != plan.plan_sha256:
        raise ValueError("configuration does not match experiment plan")

    expected_backend_ids = tuple(sorted({backend for cell in plan.cells for backend in cell.available_backends}))
    actual_backend_ids = tuple(row.backend_id for row in backend_rows)
    if actual_backend_ids != expected_backend_ids:
        raise ValueError("backend snapshot IDs must exactly match experiment plan backends")

    task_count = len(task_rows)
    replication_count = plan.replications
    trajectory_count = len(plan.cells)
    chooser_vs_fixed = task_count * len(plan.controller_ids) * 3 * replication_count
    cross_controller_chooser = task_count * replication_count
    pairwise_count = chooser_vs_fixed + cross_controller_chooser
    rating_count = trajectory_count
    expected_outputs = ExpectedOutputInventory(
        trajectory_count=trajectory_count,
        final_output_count=trajectory_count,
        max_media_call_count=sum(cell.media_call_budget for cell in plan.cells),
        rating_item_count=rating_count,
        chooser_vs_fixed_pair_count=chooser_vs_fixed,
        cross_controller_chooser_pair_count=cross_controller_chooser,
        pairwise_item_count=pairwise_count,
        responses_per_rating_item=responses_per_item,
        responses_per_pairwise_item=responses_per_item,
        base_human_response_count=(rating_count + pairwise_count) * responses_per_item,
    )

    provisional = FreezeReadyBundle(
        bundle_schema_version="thrumely.freeze-ready.v1",
        metadata=metadata,
        plan=plan,
        tasks=task_rows,
        controllers=controller_rows,
        environments=environment_rows,
        backends=backend_rows,
        expected_outputs=expected_outputs,
        bundle_sha256="",
    )
    return replace(provisional, bundle_sha256=compute_freeze_bundle_sha256(provisional))
