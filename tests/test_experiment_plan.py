from __future__ import annotations

import pytest

from thrumely.experiment_plan import compile_experiment_plan
from thrumely.schema import ControllerConfig, TaskSpec, ToolEnvironment


def make_tasks(n: int = 3):
    return tuple(
        TaskSpec(task_id=f"task-{i:03d}", family="synthetic", instruction=f"Instruction {i}")
        for i in range(n)
    )


def make_controllers():
    return (
        ControllerConfig(controller_id="controller-b", provider="p2", model="m2"),
        ControllerConfig(controller_id="controller-a", provider="p1", model="m1"),
    )


def make_envs():
    return (
        ToolEnvironment("fixed-z", "fixed", ("backend-z",), 2),
        ToolEnvironment("chooser", "chooser", ("backend-y", "backend-z", "backend-x"), 2),
        ToolEnvironment("fixed-x", "fixed", ("backend-x",), 2),
        ToolEnvironment("fixed-y", "fixed", ("backend-y",), 2),
    )


def test_plan_is_deterministic_and_input_order_independent():
    tasks = make_tasks()
    controllers = make_controllers()
    envs = make_envs()
    a = compile_experiment_plan(tasks, controllers, envs)
    b = compile_experiment_plan(tuple(reversed(tasks)), tuple(reversed(controllers)), tuple(reversed(envs)))
    assert a.plan_sha256 == b.plan_sha256
    assert a.cells == b.cells
    assert len(a.cells) == 3 * 2 * 4 * 2
    assert len({cell.cell_id for cell in a.cells}) == len(a.cells)
    assert all(cell.media_call_budget == 2 for cell in a.cells)


def test_future_v1_arithmetic_is_1600_cells():
    plan = compile_experiment_plan(make_tasks(100), make_controllers(), make_envs())
    assert len(plan.cells) == 1600


@pytest.mark.parametrize(
    ("controllers", "envs", "message"),
    [
        ((ControllerConfig("only", "p", "m"),), make_envs(), "exactly two controllers"),
        (make_controllers(), make_envs()[:3], "exactly four environments"),
        (
            make_controllers(),
            (
                ToolEnvironment("f1", "fixed", ("a",), 2),
                ToolEnvironment("f2", "fixed", ("b",), 2),
                ToolEnvironment("c1", "chooser", ("a", "b", "c"), 2),
                ToolEnvironment("c2", "chooser", ("a", "b", "c"), 2),
            ),
            "three fixed environments and one chooser",
        ),
        (
            make_controllers(),
            (
                ToolEnvironment("f1", "fixed", ("a",), 2),
                ToolEnvironment("f2", "fixed", ("b",), 2),
                ToolEnvironment("f3", "fixed", ("c",), 2),
                ToolEnvironment("chooser", "chooser", ("a", "b", "d"), 2),
            ),
            "chooser backends must equal fixed backends",
        ),
        (
            make_controllers(),
            (
                ToolEnvironment("f1", "fixed", ("a",), 1),
                ToolEnvironment("f2", "fixed", ("b",), 2),
                ToolEnvironment("f3", "fixed", ("c",), 2),
                ToolEnvironment("chooser", "chooser", ("a", "b", "c"), 2),
            ),
            "media_call_budget must be exactly 2",
        ),
    ],
)
def test_invalid_structure_fails_closed(controllers, envs, message):
    with pytest.raises(ValueError, match=message):
        compile_experiment_plan(make_tasks(), controllers, envs)


def test_duplicate_identity_ids_are_rejected():
    tasks = (make_tasks(1)[0], make_tasks(1)[0])
    with pytest.raises(ValueError, match="duplicate task_id"):
        compile_experiment_plan(tasks, make_controllers(), make_envs())

    controllers = (make_controllers()[0], make_controllers()[0])
    with pytest.raises(ValueError, match="duplicate controller_id"):
        compile_experiment_plan(make_tasks(), controllers, make_envs())

    env = make_envs()[0]
    with pytest.raises(ValueError, match="duplicate environment_id"):
        compile_experiment_plan(make_tasks(), make_controllers(), (env, env, make_envs()[1], make_envs()[2]))


def test_replications_must_be_positive_integer():
    with pytest.raises(ValueError, match="replications must be a positive integer"):
        compile_experiment_plan(make_tasks(), make_controllers(), make_envs(), replications=0)
    with pytest.raises(ValueError, match="replications must be a positive integer"):
        compile_experiment_plan(make_tasks(), make_controllers(), make_envs(), replications=True)


def test_task_or_controller_configuration_drift_changes_plan_and_cell_identity():
    tasks = make_tasks(1)
    controllers = make_controllers()
    envs = make_envs()
    baseline = compile_experiment_plan(tasks, controllers, envs)

    changed_task = (
        TaskSpec(task_id=tasks[0].task_id, family=tasks[0].family, instruction="Changed instruction"),
    )
    task_plan = compile_experiment_plan(changed_task, controllers, envs)
    assert task_plan.plan_sha256 != baseline.plan_sha256
    assert {cell.cell_id for cell in task_plan.cells} != {cell.cell_id for cell in baseline.cells}

    changed_controllers = (
        ControllerConfig(
            controller_id=controllers[0].controller_id,
            provider=controllers[0].provider,
            model="changed-model",
        ),
        controllers[1],
    )
    controller_plan = compile_experiment_plan(tasks, changed_controllers, envs)
    assert controller_plan.plan_sha256 != baseline.plan_sha256
    baseline_changed_controller_cells = {
        cell.cell_id for cell in baseline.cells if cell.controller_id == controllers[0].controller_id
    }
    changed_controller_cells = {
        cell.cell_id for cell in controller_plan.cells if cell.controller_id == controllers[0].controller_id
    }
    assert changed_controller_cells != baseline_changed_controller_cells
