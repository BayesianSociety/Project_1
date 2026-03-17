from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class WorkflowError(Exception):
    """Base class for workflow errors."""


class PreflightError(WorkflowError):
    """Raised when environment requirements are not met."""


class PlannerValidationError(WorkflowError):
    """Raised when the architect plan is invalid."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


class AllowlistViolationError(WorkflowError):
    """Raised when a worker touches paths outside its allowlist."""


@dataclass(slots=True)
class RuntimeConfig:
    model: str = "gpt-5-codex"
    sandbox_mode: str = "workspace-write"
    approval_policy: str = "never"
    workspace_root: Path = Path(".")
    output_root: Path = Path(".codex_multi_agent")
    project_description: str = "Project_description.md"
    max_parallel_workers: int = 2
    planner_repair_attempts: int = 2
    worker_retries: int = 2
    step_timeout_seconds: int = 1800
    frozen_inputs: tuple[str, ...] = ("Project_description.md",)
    verbose: bool = True


@dataclass(slots=True)
class ValidationRule:
    id: str
    kind: str
    target: str
    expectation: str

    @classmethod
    def from_dict(cls, data: dict[str, Any], prefix: str) -> "ValidationRule":
        missing = [key for key in ("id", "kind", "target", "expectation") if not isinstance(data.get(key), str) or not data[key].strip()]
        if missing:
            raise PlannerValidationError([f"{prefix}: missing or invalid validation rule field(s): {', '.join(missing)}"])
        return cls(
            id=data["id"].strip(),
            kind=data["kind"].strip(),
            target=data["target"].strip(),
            expectation=data["expectation"].strip(),
        )


@dataclass(slots=True)
class PlanTask:
    task_id: str
    role: str
    summary: str
    owned_paths: list[str]
    required_outputs: list[str]
    dependencies: list[str]
    contracts: list[str]
    validation_rules: list[ValidationRule]
    build_expectations: list[str]
    runtime_expectations: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int) -> "PlanTask":
        prefix = f"tasks[{index}]"
        errors: list[str] = []
        for key in ("task_id", "role", "summary"):
            value = data.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{prefix}.{key}: expected non-empty string")

        def require_path_list(field_name: str) -> list[str]:
            value = data.get(field_name)
            if not isinstance(value, list) or not value:
                errors.append(f"{prefix}.{field_name}: expected non-empty list of relative file paths")
                return []
            parsed: list[str] = []
            for item in value:
                if not isinstance(item, str) or not item.strip():
                    errors.append(f"{prefix}.{field_name}: contains empty item")
                    continue
                candidate = item.strip()
                if candidate.startswith("/") or candidate.endswith("/"):
                    errors.append(f"{prefix}.{field_name}: '{candidate}' must be a concrete relative file path")
                    continue
                parsed.append(candidate)
            return parsed

        def require_string_list(field_name: str) -> list[str]:
            value = data.get(field_name)
            if not isinstance(value, list):
                errors.append(f"{prefix}.{field_name}: expected list of strings")
                return []
            parsed: list[str] = []
            for item in value:
                if not isinstance(item, str) or not item.strip():
                    errors.append(f"{prefix}.{field_name}: contains empty item")
                    continue
                parsed.append(item.strip())
            return parsed

        owned_paths = require_path_list("owned_paths")
        required_outputs = require_path_list("required_outputs")
        dependencies = require_string_list("dependencies")
        contracts = require_string_list("contracts")
        build_expectations = require_string_list("build_expectations")
        runtime_expectations = require_string_list("runtime_expectations")

        rules_raw = data.get("validation_rules")
        validation_rules: list[ValidationRule] = []
        if not isinstance(rules_raw, list) or not rules_raw:
            errors.append(f"{prefix}.validation_rules: expected non-empty list")
        else:
            for rule_index, rule_data in enumerate(rules_raw):
                if not isinstance(rule_data, dict):
                    errors.append(f"{prefix}.validation_rules[{rule_index}]: expected object")
                    continue
                try:
                    validation_rules.append(
                        ValidationRule.from_dict(rule_data, f"{prefix}.validation_rules[{rule_index}]")
                    )
                except PlannerValidationError as exc:
                    errors.extend(exc.errors)

        if errors:
            raise PlannerValidationError(errors)

        return cls(
            task_id=data["task_id"].strip(),
            role=data["role"].strip(),
            summary=data["summary"].strip(),
            owned_paths=owned_paths,
            required_outputs=required_outputs,
            dependencies=dependencies,
            contracts=contracts,
            validation_rules=validation_rules,
            build_expectations=build_expectations,
            runtime_expectations=runtime_expectations,
        )


@dataclass(slots=True)
class PlannerDocument:
    task_summary: str
    roles: list[str]
    tasks: list[PlanTask]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlannerDocument":
        errors: list[str] = []
        task_summary = data.get("task_summary")
        if not isinstance(task_summary, str) or not task_summary.strip():
            errors.append("task_summary: expected non-empty string")

        roles = data.get("roles")
        if not isinstance(roles, list) or not roles:
            errors.append("roles: expected non-empty list")
            parsed_roles: list[str] = []
        else:
            parsed_roles = []
            for role in roles:
                if not isinstance(role, str) or not role.strip():
                    errors.append("roles: contains empty item")
                    continue
                parsed_roles.append(role.strip())

        tasks_raw = data.get("tasks")
        parsed_tasks: list[PlanTask] = []
        if not isinstance(tasks_raw, list) or not tasks_raw:
            errors.append("tasks: expected non-empty list")
        else:
            for index, item in enumerate(tasks_raw):
                if not isinstance(item, dict):
                    errors.append(f"tasks[{index}]: expected object")
                    continue
                try:
                    parsed_tasks.append(PlanTask.from_dict(item, index))
                except PlannerValidationError as exc:
                    errors.extend(exc.errors)

        ownership_map: dict[str, str] = {}
        for task in parsed_tasks:
            for owned_path in task.owned_paths:
                prior = ownership_map.get(owned_path)
                if prior and prior != task.task_id:
                    errors.append(
                        f"owned_paths overlap: '{owned_path}' owned by both {prior} and {task.task_id}"
                    )
                ownership_map[owned_path] = task.task_id

        task_ids = {task.task_id for task in parsed_tasks}
        for task in parsed_tasks:
            for dependency in task.dependencies:
                if dependency not in task_ids:
                    errors.append(f"{task.task_id}.dependencies: unknown task_id '{dependency}'")

        if errors:
            raise PlannerValidationError(errors)

        return cls(
            task_summary=task_summary.strip(),
            roles=parsed_roles,
            tasks=parsed_tasks,
        )


@dataclass(slots=True)
class StepResult:
    role: str
    status: str
    message: str
    payload: dict[str, Any]
    stdout: str
    stderr: str
    changed_files: list[str] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)
    manifest_path: Path | None = None

