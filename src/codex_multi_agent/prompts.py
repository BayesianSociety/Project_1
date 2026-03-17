from __future__ import annotations

import json
from pathlib import Path

from .models import PlanTask, RuntimeConfig


RESULT_MARKER_BEGIN = "ROLE_RESULT_JSON_BEGIN"
RESULT_MARKER_END = "ROLE_RESULT_JSON_END"


def system_runtime_block(config: RuntimeConfig) -> str:
    return (
        "Runtime configuration:\n"
        f"- model: {config.model}\n"
        f"- sandbox mode: {config.sandbox_mode}\n"
        f"- approval policy: {config.approval_policy}\n"
        f"- workspace root: {config.workspace_root}\n"
        f"- canonical output root: {config.output_root}\n"
        f"- timeout policy: {config.step_timeout_seconds} seconds per step\n"
        "- execution rule: do not be silent; narrate actions and decisions as you work\n"
    )


def _json_contract(instructions: str) -> str:
    return (
        f"Return your final result exactly between {RESULT_MARKER_BEGIN} and {RESULT_MARKER_END}.\n"
        "Inside the markers, emit valid JSON and nothing else.\n"
        f"{instructions}\n"
    )


def context_analyst_prompt(project_description: str, config: RuntimeConfig) -> str:
    return (
        "You are the Context Analyst.\n"
        f"{system_runtime_block(config)}\n"
        "Read the project brief and repository context. Extract domain, constraints, success criteria, assumptions, missing information, stack expectations, and validation expectations.\n"
        + _json_contract(
            'JSON shape: {"status":"ok","domain":"...","constraints":["..."],"success_criteria":["..."],"assumptions":["..."],"missing_information":["..."],"stack_requirements":["..."],"validation_expectations":["..."],"repo_constraints":["..."]}'
        )
        + "\nProject brief:\n"
        + project_description
    )


def architect_prompt(
    project_description: str,
    context_payload: dict,
    config: RuntimeConfig,
    repair_errors: list[str] | None = None,
) -> str:
    repair_block = ""
    if repair_errors:
        repair_block = (
            "\nPlanner repair request. Fix these exact validation failures and preserve all valid prior intent:\n"
            + "\n".join(f"- {error}" for error in repair_errors)
            + "\n"
        )
    return (
        "You are the Architect.\n"
        f"{system_runtime_block(config)}\n"
        "Produce a machine-checkable implementation plan for the Orchestrator.\n"
        "Rules:\n"
        "- every owned_paths entry must be a concrete relative file path\n"
        "- every required_outputs entry must be a concrete relative file path\n"
        "- no overlapping ownership\n"
        "- dependencies must reference task_id values from the same plan\n"
        "- validation rules must use durable evidence, not wording preference\n"
        "- keep the agent count small and use only the required execution roles when appropriate\n"
        + repair_block
        + _json_contract(
            '{"task_summary":"...","roles":["Context Analyst","Architect","Backend Producer","Frontend Producer","Verification Agent"],"tasks":[{"task_id":"backend-1","role":"Backend Producer","summary":"...","owned_paths":["relative/path.py"],"required_outputs":["relative/path.py"],"dependencies":["architect"],"contracts":["contract file or rule"],"validation_rules":[{"id":"rule-1","kind":"artifact_read","target":"relative/path.py","expectation":"..."}],"build_expectations":["command or expectation"],"runtime_expectations":["command or expectation"]}]}'
        )
        + "\nContext Analyst output:\n"
        + json.dumps(context_payload, indent=2, sort_keys=True)
        + "\nProject brief:\n"
        + project_description
    )


def worker_prompt(
    role: str,
    task: PlanTask,
    plan_summary: str,
    project_description: str,
    config: RuntimeConfig,
    workspace_root: Path,
) -> str:
    task_blob = {
        "task_id": task.task_id,
        "summary": task.summary,
        "owned_paths": task.owned_paths,
        "required_outputs": task.required_outputs,
        "dependencies": task.dependencies,
        "contracts": task.contracts,
        "validation_rules": [rule.__dict__ for rule in task.validation_rules],
        "build_expectations": task.build_expectations,
        "runtime_expectations": task.runtime_expectations,
    }
    forbidden = ["Do not modify any file outside owned_paths and required_outputs."]
    return (
        f"You are the {role}.\n"
        f"{system_runtime_block(config)}\n"
        "You are working in an isolated git worktree.\n"
        f"Workspace: {workspace_root}\n"
        f"Plan summary: {plan_summary}\n"
        "Task contract:\n"
        f"{json.dumps(task_blob, indent=2, sort_keys=True)}\n"
        "Execution rules:\n"
        "- narrate your actions as you work\n"
        "- report blockers immediately\n"
        "- preserve contracts defined by the Architect\n"
        + "\n".join(f"- {item}" for item in forbidden)
        + "\n"
        + _json_contract(
            '{"status":"ok","task_id":"...","summary":"...","changed_files":["relative/path"],"blockers":[],"notes":["..."]}'
        )
        + "\nProject brief:\n"
        + project_description
    )


def verification_prompt(
    project_description: str,
    plan_payload: dict,
    config: RuntimeConfig,
    artifacts_summary: dict,
) -> str:
    return (
        "You are the Verification Agent.\n"
        f"{system_runtime_block(config)}\n"
        "Review the completed artifacts against the project brief and plan. Focus on artifact-aware evidence, contract consistency, build viability, runtime viability, and user-facing clarity where relevant.\n"
        + _json_contract(
            '{"status":"ok","artifact_checks":[{"path":"relative/path","result":"pass","evidence":"..."}],"build_checks":["..."],"runtime_checks":["..."],"acceptance":["..."],"failures":["..."]}'
        )
        + "\nPlan:\n"
        + json.dumps(plan_payload, indent=2, sort_keys=True)
        + "\nArtifacts summary:\n"
        + json.dumps(artifacts_summary, indent=2, sort_keys=True)
        + "\nProject brief:\n"
        + project_description
    )
