from __future__ import annotations

import json

from .annotation_manifest import compile_annotation_manifests
from .experiment_plan import compile_experiment_plan
from .schema import CompletionStatus, ControllerConfig, TaskSpec, ToolEnvironment, TrajectoryRecord


def _tasks() -> tuple[TaskSpec, ...]:
    return tuple(
        TaskSpec(
            task_id=f"synthetic-task-{index}",
            family="synthetic-only",
            instruction=f"Synthetic instruction {index}",
        )
        for index in range(1, 4)
    )


def _controllers() -> tuple[ControllerConfig, ...]:
    return (
        ControllerConfig("synthetic-controller-a", "synthetic", "model-a"),
        ControllerConfig("synthetic-controller-b", "synthetic", "model-b"),
    )


def _environments() -> tuple[ToolEnvironment, ...]:
    return (
        ToolEnvironment("chooser", "chooser", ("backend-a", "backend-b", "backend-c"), 2),
        ToolEnvironment("fixed-a", "fixed", ("backend-a",), 2),
        ToolEnvironment("fixed-b", "fixed", ("backend-b",), 2),
        ToolEnvironment("fixed-c", "fixed", ("backend-c",), 2),
    )


def build_synthetic_report() -> dict[str, object]:
    tasks = _tasks()
    plan = compile_experiment_plan(
        tasks,
        _controllers(),
        _environments(),
        data_classification="synthetic-unfrozen-planning",
    )
    trajectories = tuple(
        TrajectoryRecord(
            trajectory_id=f"synthetic-traj-{cell.cell_id}",
            task_id=cell.task_id,
            controller_id=cell.controller_id,
            environment_id=cell.environment_id,
            replication=cell.replication,
            tool_calls=(),
            final_artifact_id=f"synthetic-artifact-{cell.cell_id}",
            completion_status=CompletionStatus.SUCCESS,
            infrastructure_error=None,
        )
        for cell in plan.cells
    )
    bundle = compile_annotation_manifests(
        plan,
        {task.task_id: task.instruction for task in tasks},
        trajectories,
    )
    chooser_vs_fixed = sum(item.pair_kind == "chooser_vs_fixed" for item in bundle.pairwise)
    cross_controller = sum(
        item.pair_kind == "cross_controller_chooser" for item in bundle.pairwise
    )
    return {
        "mode": "SYNTHETIC_EXPERIMENT_PLAN_ONLY",
        "data_classification": plan.data_classification,
        "network_calls": 0,
        "hosted_calls": 0,
        "datapoint_jobs": 0,
        "credits_spent": 0,
        "tasks": len(plan.task_ids),
        "controllers": len(plan.controller_ids),
        "environments": len(plan.environment_ids),
        "replications": plan.replications,
        "trajectory_cells": len(plan.cells),
        "rating_items": bundle.rating_count,
        "pairwise_items": bundle.pairwise_count,
        "chooser_vs_fixed_items": chooser_vs_fixed,
        "cross_controller_chooser_items": cross_controller,
        "plan_sha256": plan.plan_sha256,
        "manifest_sha256": bundle.manifest_sha256,
    }


def main() -> int:
    print(json.dumps(build_synthetic_report(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
