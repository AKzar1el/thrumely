from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .experiment_plan import ExperimentPlan
from .hashing import content_hash
from .schema import CompletionStatus, TrajectoryRecord


@dataclass(frozen=True)
class RatingAnnotationItem:
    annotation_item_id: str
    task_id: str
    instruction: str
    trajectory_id: str
    artifact_id: str
    controller_id: str
    environment_id: str
    replication: int


@dataclass(frozen=True)
class PairwiseAnnotationItem:
    annotation_item_id: str
    pair_kind: str
    task_id: str
    instruction: str
    trajectory_a_id: str
    artifact_a_id: str
    controller_a_id: str
    environment_a_id: str
    trajectory_b_id: str
    artifact_b_id: str
    controller_b_id: str
    environment_b_id: str
    replication: int


@dataclass(frozen=True)
class AnnotationManifestBundle:
    plan_sha256: str
    ratings: tuple[RatingAnnotationItem, ...]
    pairwise: tuple[PairwiseAnnotationItem, ...]
    rating_count: int
    pairwise_count: int
    manifest_sha256: str


def _cell_key(
    task_id: str,
    controller_id: str,
    environment_id: str,
    replication: int,
) -> tuple[str, str, str, int]:
    return task_id, controller_id, environment_id, replication


def _rating_item(
    plan_sha256: str,
    instruction: str,
    trajectory: TrajectoryRecord,
) -> RatingAnnotationItem:
    assert trajectory.final_artifact_id is not None
    identity = {
        "plan_sha256": plan_sha256,
        "task_id": trajectory.task_id,
        "trajectory_id": trajectory.trajectory_id,
        "artifact_id": trajectory.final_artifact_id,
        "controller_id": trajectory.controller_id,
        "environment_id": trajectory.environment_id,
        "replication": trajectory.replication,
    }
    return RatingAnnotationItem(
        annotation_item_id=f"rating-{content_hash(identity)}",
        task_id=trajectory.task_id,
        instruction=instruction,
        trajectory_id=trajectory.trajectory_id,
        artifact_id=trajectory.final_artifact_id,
        controller_id=trajectory.controller_id,
        environment_id=trajectory.environment_id,
        replication=trajectory.replication,
    )


def _pair_item(
    *,
    plan_sha256: str,
    pair_kind: str,
    instruction: str,
    trajectory_a: TrajectoryRecord,
    trajectory_b: TrajectoryRecord,
) -> PairwiseAnnotationItem:
    assert trajectory_a.final_artifact_id is not None
    assert trajectory_b.final_artifact_id is not None
    if trajectory_a.task_id != trajectory_b.task_id or trajectory_a.replication != trajectory_b.replication:
        raise ValueError("pairwise trajectories must share task and replication")
    identity = {
        "plan_sha256": plan_sha256,
        "pair_kind": pair_kind,
        "task_id": trajectory_a.task_id,
        "trajectory_a_id": trajectory_a.trajectory_id,
        "artifact_a_id": trajectory_a.final_artifact_id,
        "controller_a_id": trajectory_a.controller_id,
        "environment_a_id": trajectory_a.environment_id,
        "trajectory_b_id": trajectory_b.trajectory_id,
        "artifact_b_id": trajectory_b.final_artifact_id,
        "controller_b_id": trajectory_b.controller_id,
        "environment_b_id": trajectory_b.environment_id,
        "replication": trajectory_a.replication,
    }
    return PairwiseAnnotationItem(
        annotation_item_id=f"pair-{content_hash(identity)}",
        pair_kind=pair_kind,
        task_id=trajectory_a.task_id,
        instruction=instruction,
        trajectory_a_id=trajectory_a.trajectory_id,
        artifact_a_id=trajectory_a.final_artifact_id,
        controller_a_id=trajectory_a.controller_id,
        environment_a_id=trajectory_a.environment_id,
        trajectory_b_id=trajectory_b.trajectory_id,
        artifact_b_id=trajectory_b.final_artifact_id,
        controller_b_id=trajectory_b.controller_id,
        environment_b_id=trajectory_b.environment_id,
        replication=trajectory_a.replication,
    )


def compile_annotation_manifests(
    plan: ExperimentPlan,
    task_instructions: Mapping[str, str],
    trajectories: Iterable[TrajectoryRecord],
) -> AnnotationManifestBundle:
    instructions: dict[str, str] = {}
    for task_id in plan.task_ids:
        instruction = task_instructions.get(task_id)
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError(f"missing instruction for task_id: {task_id}")
        instructions[task_id] = instruction

    planned_keys = {
        _cell_key(cell.task_id, cell.controller_id, cell.environment_id, cell.replication)
        for cell in plan.cells
    }
    rows_by_key: dict[tuple[str, str, str, int], TrajectoryRecord] = {}
    trajectory_ids: set[str] = set()
    for trajectory in trajectories:
        if not isinstance(trajectory, TrajectoryRecord):
            raise ValueError("trajectories must contain TrajectoryRecord rows")
        if trajectory.trajectory_id in trajectory_ids:
            raise ValueError(f"duplicate trajectory_id: {trajectory.trajectory_id}")
        trajectory_ids.add(trajectory.trajectory_id)
        key = _cell_key(
            trajectory.task_id,
            trajectory.controller_id,
            trajectory.environment_id,
            trajectory.replication,
        )
        if key not in planned_keys:
            raise ValueError(f"trajectory outside experiment plan: {key!r}")
        if key in rows_by_key:
            raise ValueError(f"duplicate trajectory for planned cell: {key!r}")
        if trajectory.completion_status is not CompletionStatus.SUCCESS or not trajectory.final_artifact_id:
            raise ValueError(
                f"trajectory must be successful with a final artifact: {trajectory.trajectory_id}"
            )
        rows_by_key[key] = trajectory

    missing = [
        _cell_key(cell.task_id, cell.controller_id, cell.environment_id, cell.replication)
        for cell in plan.cells
        if _cell_key(cell.task_id, cell.controller_id, cell.environment_id, cell.replication)
        not in rows_by_key
    ]
    if missing:
        raise ValueError(f"missing trajectory for planned cell: {missing[0]!r}")

    ratings = tuple(
        _rating_item(
            plan.plan_sha256,
            instructions[cell.task_id],
            rows_by_key[
                _cell_key(cell.task_id, cell.controller_id, cell.environment_id, cell.replication)
            ],
        )
        for cell in plan.cells
    )

    environment_modes: dict[str, str] = {}
    for cell in plan.cells:
        environment_modes[cell.environment_id] = cell.environment_mode
    chooser_ids = sorted(env_id for env_id, mode in environment_modes.items() if mode == "chooser")
    fixed_ids = sorted(env_id for env_id, mode in environment_modes.items() if mode == "fixed")
    if len(chooser_ids) != 1 or len(fixed_ids) != 3:
        raise ValueError("experiment plan must expose one chooser and three fixed environments")
    chooser_id = chooser_ids[0]

    pairwise: list[PairwiseAnnotationItem] = []
    for task_id in plan.task_ids:
        instruction = instructions[task_id]
        for replication in range(1, plan.replications + 1):
            for controller_id in plan.controller_ids:
                chooser = rows_by_key[_cell_key(task_id, controller_id, chooser_id, replication)]
                for fixed_id in fixed_ids:
                    fixed = rows_by_key[_cell_key(task_id, controller_id, fixed_id, replication)]
                    pairwise.append(
                        _pair_item(
                            plan_sha256=plan.plan_sha256,
                            pair_kind="chooser_vs_fixed",
                            instruction=instruction,
                            trajectory_a=chooser,
                            trajectory_b=fixed,
                        )
                    )
            controller_a, controller_b = plan.controller_ids
            pairwise.append(
                _pair_item(
                    plan_sha256=plan.plan_sha256,
                    pair_kind="cross_controller_chooser",
                    instruction=instruction,
                    trajectory_a=rows_by_key[
                        _cell_key(task_id, controller_a, chooser_id, replication)
                    ],
                    trajectory_b=rows_by_key[
                        _cell_key(task_id, controller_b, chooser_id, replication)
                    ],
                )
            )

    rating_rows = tuple(ratings)
    pairwise_rows = tuple(pairwise)
    manifest_payload = {
        "plan_sha256": plan.plan_sha256,
        "ratings": rating_rows,
        "pairwise": pairwise_rows,
        "rating_count": len(rating_rows),
        "pairwise_count": len(pairwise_rows),
    }
    manifest_sha256 = content_hash(manifest_payload)
    return AnnotationManifestBundle(
        plan_sha256=plan.plan_sha256,
        ratings=rating_rows,
        pairwise=pairwise_rows,
        rating_count=len(rating_rows),
        pairwise_count=len(pairwise_rows),
        manifest_sha256=manifest_sha256,
    )
