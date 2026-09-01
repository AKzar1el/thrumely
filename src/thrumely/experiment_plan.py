from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .hashing import content_hash
from .schema import ControllerConfig, TaskSpec, ToolEnvironment


@dataclass(frozen=True)
class ExperimentCell:
    cell_id: str
    task_id: str
    task_spec_sha256: str
    controller_id: str
    controller_config_sha256: str
    environment_id: str
    environment_config_sha256: str
    replication: int
    environment_mode: str
    available_backends: tuple[str, ...]
    media_call_budget: int


@dataclass(frozen=True)
class ExperimentPlan:
    plan_id: str
    plan_sha256: str
    data_classification: str
    task_ids: tuple[str, ...]
    task_spec_sha256s: tuple[tuple[str, str], ...]
    controller_ids: tuple[str, ...]
    controller_config_sha256s: tuple[tuple[str, str], ...]
    environment_ids: tuple[str, ...]
    environment_config_sha256s: tuple[tuple[str, str], ...]
    replications: int
    cells: tuple[ExperimentCell, ...]


def _unique_by_id(items: Iterable[object], attr: str, label: str) -> tuple[object, ...]:
    values = tuple(items)
    seen: set[str] = set()
    for item in values:
        value = getattr(item, attr)
        if value in seen:
            raise ValueError(f"duplicate {label}: {value}")
        seen.add(value)
    return values


def _task_identity(task: TaskSpec) -> dict[str, object]:
    return {
        "task_id": task.task_id,
        "family": task.family,
        "instruction": task.instruction,
    }


def _controller_identity(controller: ControllerConfig) -> dict[str, object]:
    return {
        "controller_id": controller.controller_id,
        "provider": controller.provider,
        "model": controller.model,
        "reasoning_effort": controller.reasoning_effort,
        "max_output_tokens": controller.max_output_tokens,
        "system_prompt_sha256": controller.system_prompt_sha256,
        "sdk_version": controller.sdk_version,
    }


def _environment_identity(environment: ToolEnvironment) -> dict[str, object]:
    return {
        "environment_id": environment.environment_id,
        "mode": environment.mode,
        "available_backends": tuple(sorted(environment.available_backends)),
        "media_call_budget": environment.media_call_budget,
    }


def compile_experiment_plan(
    tasks: Iterable[TaskSpec],
    controllers: Iterable[ControllerConfig],
    environments: Iterable[ToolEnvironment],
    *,
    replications: int = 2,
    data_classification: str = "unfrozen-planning",
) -> ExperimentPlan:
    if not isinstance(replications, int) or isinstance(replications, bool) or replications < 1:
        raise ValueError("replications must be a positive integer")
    if not isinstance(data_classification, str) or not data_classification.strip():
        raise ValueError("data_classification must be a non-empty string")

    task_rows = _unique_by_id(tasks, "task_id", "task_id")
    controller_rows = _unique_by_id(controllers, "controller_id", "controller_id")
    environment_rows = _unique_by_id(environments, "environment_id", "environment_id")

    if not task_rows:
        raise ValueError("at least one task is required")
    if len(controller_rows) != 2:
        raise ValueError("experiment plan requires exactly two controllers")
    if len(environment_rows) != 4:
        raise ValueError("experiment plan requires exactly four environments")

    fixed = tuple(env for env in environment_rows if env.mode == "fixed")
    chooser = tuple(env for env in environment_rows if env.mode == "chooser")
    if len(fixed) != 3 or len(chooser) != 1:
        raise ValueError("experiment plan requires three fixed environments and one chooser")
    if any(env.media_call_budget != 2 for env in environment_rows):
        raise ValueError("environment media_call_budget must be exactly 2")

    fixed_backends = tuple(sorted(env.available_backends[0] for env in fixed))
    if len(set(fixed_backends)) != 3:
        raise ValueError("fixed environments must use three distinct backends")
    chooser_backends = tuple(sorted(chooser[0].available_backends))
    if chooser_backends != fixed_backends:
        raise ValueError("chooser backends must equal fixed backends")

    sorted_tasks = tuple(sorted(task_rows, key=lambda item: item.task_id))
    sorted_controllers = tuple(sorted(controller_rows, key=lambda item: item.controller_id))
    sorted_envs = tuple(sorted(environment_rows, key=lambda item: item.environment_id))

    task_hashes = {task.task_id: content_hash(_task_identity(task)) for task in sorted_tasks}
    controller_hashes = {
        controller.controller_id: content_hash(_controller_identity(controller))
        for controller in sorted_controllers
    }
    environment_hashes = {
        environment.environment_id: content_hash(_environment_identity(environment))
        for environment in sorted_envs
    }

    cells: list[ExperimentCell] = []
    for task in sorted_tasks:
        for controller in sorted_controllers:
            for environment in sorted_envs:
                backends = tuple(sorted(environment.available_backends))
                for replication in range(1, replications + 1):
                    identity = {
                        "task_id": task.task_id,
                        "task_spec_sha256": task_hashes[task.task_id],
                        "controller_id": controller.controller_id,
                        "controller_config_sha256": controller_hashes[controller.controller_id],
                        "environment_id": environment.environment_id,
                        "environment_config_sha256": environment_hashes[environment.environment_id],
                        "replication": replication,
                        "environment_mode": environment.mode,
                        "available_backends": backends,
                        "media_call_budget": environment.media_call_budget,
                    }
                    cells.append(ExperimentCell(cell_id=f"cell-{content_hash(identity)}", **identity))

    task_spec_sha256s = tuple((task.task_id, task_hashes[task.task_id]) for task in sorted_tasks)
    controller_config_sha256s = tuple(
        (controller.controller_id, controller_hashes[controller.controller_id])
        for controller in sorted_controllers
    )
    environment_config_sha256s = tuple(
        (environment.environment_id, environment_hashes[environment.environment_id])
        for environment in sorted_envs
    )
    payload = {
        "data_classification": data_classification,
        "task_ids": tuple(task.task_id for task in sorted_tasks),
        "task_spec_sha256s": task_spec_sha256s,
        "controller_ids": tuple(controller.controller_id for controller in sorted_controllers),
        "controller_config_sha256s": controller_config_sha256s,
        "environment_ids": tuple(environment.environment_id for environment in sorted_envs),
        "environment_config_sha256s": environment_config_sha256s,
        "replications": replications,
        "cells": tuple(cells),
    }
    plan_sha256 = content_hash(payload)
    return ExperimentPlan(
        plan_id=f"plan-{plan_sha256}",
        plan_sha256=plan_sha256,
        data_classification=data_classification,
        task_ids=payload["task_ids"],
        task_spec_sha256s=task_spec_sha256s,
        controller_ids=payload["controller_ids"],
        controller_config_sha256s=controller_config_sha256s,
        environment_ids=payload["environment_ids"],
        environment_config_sha256s=environment_config_sha256s,
        replications=replications,
        cells=tuple(cells),
    )
