from __future__ import annotations

import pytest

from thrumely.annotation_manifest import compile_annotation_manifests
from thrumely.experiment_plan import compile_experiment_plan
from thrumely.schema import CompletionStatus, ControllerConfig, TaskSpec, ToolEnvironment, TrajectoryRecord


def make_tasks(n: int = 2):
    return tuple(
        TaskSpec(task_id=f"task-{i:03d}", family="synthetic", instruction=f"Instruction {i}")
        for i in range(n)
    )


def make_controllers():
    return (
        ControllerConfig("controller-a", "p1", "m1"),
        ControllerConfig("controller-b", "p2", "m2"),
    )


def make_envs():
    return (
        ToolEnvironment("chooser", "chooser", ("backend-a", "backend-b", "backend-c"), 2),
        ToolEnvironment("fixed-a", "fixed", ("backend-a",), 2),
        ToolEnvironment("fixed-b", "fixed", ("backend-b",), 2),
        ToolEnvironment("fixed-c", "fixed", ("backend-c",), 2),
    )


def make_plan(n: int = 2):
    return compile_experiment_plan(make_tasks(n), make_controllers(), make_envs())


def success_trajectories(plan):
    return tuple(
        TrajectoryRecord(
            trajectory_id=f"traj-{cell.cell_id}",
            task_id=cell.task_id,
            controller_id=cell.controller_id,
            environment_id=cell.environment_id,
            replication=cell.replication,
            tool_calls=(),
            final_artifact_id=f"artifact-{cell.cell_id}",
            completion_status=CompletionStatus.SUCCESS,
            infrastructure_error=None,
        )
        for cell in plan.cells
    )


def instructions(n: int = 2):
    return {task.task_id: task.instruction for task in make_tasks(n)}


def test_manifest_joins_by_scientific_identity_not_row_order():
    plan = make_plan()
    rows = tuple(reversed(success_trajectories(plan)))
    bundle = compile_annotation_manifests(plan, instructions(), rows)
    assert bundle.rating_count == len(plan.cells) == 32
    assert bundle.pairwise_count == 28
    first = bundle.ratings[0]
    expected_cell = plan.cells[0]
    assert first.task_id == expected_cell.task_id
    assert first.controller_id == expected_cell.controller_id
    assert first.environment_id == expected_cell.environment_id
    assert first.replication == expected_cell.replication
    assert first.trajectory_id == f"traj-{expected_cell.cell_id}"


def test_pairwise_families_and_candidate_identity_are_deterministic():
    plan = make_plan()
    rows = success_trajectories(plan)
    a = compile_annotation_manifests(plan, instructions(), rows)
    b = compile_annotation_manifests(
        plan,
        dict(reversed(tuple(instructions().items()))),
        tuple(reversed(rows)),
    )
    assert a.manifest_sha256 == b.manifest_sha256
    assert a.ratings == b.ratings
    assert a.pairwise == b.pairwise
    chooser_fixed = [item for item in a.pairwise if item.pair_kind == "chooser_vs_fixed"]
    cross = [item for item in a.pairwise if item.pair_kind == "cross_controller_chooser"]
    assert len(chooser_fixed) == 24
    assert len(cross) == 4
    assert all(item.environment_a_id == "chooser" for item in chooser_fixed)
    assert all(item.environment_b_id.startswith("fixed-") for item in chooser_fixed)
    assert all(item.environment_a_id == item.environment_b_id == "chooser" for item in cross)
    assert all(item.controller_a_id < item.controller_b_id for item in cross)


def test_future_v1_manifest_arithmetic_is_1600_ratings_and_1400_pairs():
    plan = make_plan(100)
    bundle = compile_annotation_manifests(plan, instructions(100), success_trajectories(plan))
    assert bundle.rating_count == 1600
    assert bundle.pairwise_count == 1400
    assert sum(item.pair_kind == "chooser_vs_fixed" for item in bundle.pairwise) == 1200
    assert sum(item.pair_kind == "cross_controller_chooser" for item in bundle.pairwise) == 200


def test_missing_planned_cell_fails_closed():
    plan = make_plan()
    rows = success_trajectories(plan)[:-1]
    with pytest.raises(ValueError, match="missing trajectory for planned cell"):
        compile_annotation_manifests(plan, instructions(), rows)


def test_extra_trajectory_outside_plan_fails_closed():
    plan = make_plan()
    rows = list(success_trajectories(plan))
    rows.append(
        TrajectoryRecord(
            "extra-traj",
            "task-000",
            "controller-a",
            "outside",
            1,
            (),
            "artifact-extra",
            CompletionStatus.SUCCESS,
            None,
        )
    )
    with pytest.raises(ValueError, match="trajectory outside experiment plan"):
        compile_annotation_manifests(plan, instructions(), rows)


def test_duplicate_scientific_cell_fails_closed():
    plan = make_plan()
    rows = list(success_trajectories(plan))
    first = rows[0]
    rows.append(
        TrajectoryRecord(
            "other-traj",
            first.task_id,
            first.controller_id,
            first.environment_id,
            first.replication,
            (),
            "artifact-other",
            CompletionStatus.SUCCESS,
            None,
        )
    )
    with pytest.raises(ValueError, match="duplicate trajectory for planned cell"):
        compile_annotation_manifests(plan, instructions(), rows)


def test_duplicate_trajectory_id_fails_closed():
    plan = make_plan()
    rows = list(success_trajectories(plan))
    second = rows[1]
    rows[1] = TrajectoryRecord(
        rows[0].trajectory_id,
        second.task_id,
        second.controller_id,
        second.environment_id,
        second.replication,
        (),
        second.final_artifact_id,
        CompletionStatus.SUCCESS,
        None,
    )
    with pytest.raises(ValueError, match="duplicate trajectory_id"):
        compile_annotation_manifests(plan, instructions(), rows)


def test_non_success_trajectory_fails_closed():
    plan = make_plan()
    rows = list(success_trajectories(plan))
    first = rows[0]
    rows[0] = TrajectoryRecord(
        first.trajectory_id,
        first.task_id,
        first.controller_id,
        first.environment_id,
        first.replication,
        (),
        None,
        CompletionStatus.ERROR,
        "synthetic failure",
    )
    with pytest.raises(ValueError, match="must be successful with a final artifact"):
        compile_annotation_manifests(plan, instructions(), rows)


def test_missing_task_instruction_fails_closed():
    plan = make_plan()
    missing = instructions()
    missing.pop("task-001")
    with pytest.raises(ValueError, match="missing instruction for task_id"):
        compile_annotation_manifests(plan, missing, success_trajectories(plan))
