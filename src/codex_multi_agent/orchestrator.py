from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path

from .codex_exec import outcome_to_step_result, run_codex_exec
from .filesystem import diff_snapshots, enforce_allowlist, snapshot_tree, write_json
from .models import PlannerDocument, PlannerValidationError, PreflightError, RuntimeConfig, StepResult, WorkflowError
from .prompts import architect_prompt, context_analyst_prompt, verification_prompt, worker_prompt


def _print_stage(config: RuntimeConfig, message: str) -> None:
    if config.verbose:
        print(f"[orchestrator] {message}", flush=True)


def _check_command(name: str) -> None:
    if shutil.which(name) is None:
        raise PreflightError(f"Missing required command-line tool: {name}")


def _run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)


def preflight(config: RuntimeConfig) -> None:
    _print_stage(config, "Stage 1/10: environment preflight")
    _check_command("codex")
    _check_command("git")
    _check_command("python3")
    brief_path = config.workspace_root / config.project_description
    if not brief_path.exists():
        raise PreflightError(
            f"Required project brief is missing: {brief_path}. Add Project_description.md before running the workflow."
        )


def load_project_description(config: RuntimeConfig) -> str:
    brief_path = config.workspace_root / config.project_description
    return brief_path.read_text(encoding="utf-8")


def ensure_output_dirs(config: RuntimeConfig) -> None:
    for child in (
        config.output_root,
        config.output_root / "manifests",
        config.output_root / "logs",
        config.output_root / "plans",
    ):
        child.mkdir(parents=True, exist_ok=True)


def write_stage_manifest(config: RuntimeConfig, stage_name: str, payload: dict) -> Path:
    manifest_path = config.output_root / "manifests" / f"{stage_name}.json"
    write_json(manifest_path, payload)
    return manifest_path


async def run_context_analysis(config: RuntimeConfig, project_description: str) -> StepResult:
    _print_stage(config, "Stage 2/10: context analysis")
    outcome = await run_codex_exec(
        context_analyst_prompt(project_description, config),
        config=config,
        cwd=config.workspace_root,
        role="Context Analyst",
    )
    result = outcome_to_step_result("Context Analyst", outcome)
    result.manifest_path = write_stage_manifest(config, "02_context_analysis", result.payload)
    return result


async def run_architect_planner(
    config: RuntimeConfig,
    project_description: str,
    context_payload: dict,
) -> tuple[PlannerDocument, StepResult]:
    _print_stage(config, "Stage 3/10: planner generation")
    repair_errors: list[str] | None = None
    last_result: StepResult | None = None
    for attempt in range(config.planner_repair_attempts + 1):
        outcome = await run_codex_exec(
            architect_prompt(project_description, context_payload, config, repair_errors=repair_errors),
            config=config,
            cwd=config.workspace_root,
            role="Architect",
        )
        result = outcome_to_step_result("Architect", outcome)
        last_result = result

        _print_stage(config, "Stage 4/10: planner schema validation")
        try:
            planner = PlannerDocument.from_dict(result.payload)
            result.manifest_path = write_stage_manifest(config, "04_planner_valid", result.payload)
            write_json(config.output_root / "plans" / "planner.json", result.payload)
            return planner, result
        except PlannerValidationError as exc:
            if attempt >= config.planner_repair_attempts:
                raise
            repair_errors = exc.errors
            write_stage_manifest(
                config,
                f"05_planner_repair_attempt_{attempt + 1}",
                {"errors": repair_errors, "prior_payload": result.payload},
            )
            _print_stage(config, f"Stage 5/10: planner repair loop attempt {attempt + 1}")

    raise WorkflowError(f"Planner loop ended unexpectedly: {last_result}")


def _git_current_branch(workspace_root: Path) -> str:
    result = _run_command(["git", "branch", "--show-current"], workspace_root)
    branch = result.stdout.strip()
    return branch or "main"


def _create_worktree(workspace_root: Path, task_id: str) -> tuple[Path, str]:
    branch_name = f"codex/{task_id}"
    worktree_root = Path(tempfile.gettempdir()) / "codex_multi_agent_worktrees" / task_id
    if worktree_root.exists():
        shutil.rmtree(worktree_root)
    worktree_root.parent.mkdir(parents=True, exist_ok=True)
    base_branch = _git_current_branch(workspace_root)
    create = _run_command(["git", "worktree", "add", "-B", branch_name, str(worktree_root), base_branch], workspace_root)
    if create.returncode != 0:
        raise WorkflowError(f"Failed to create worktree for {task_id}: {create.stderr.strip()}")
    return worktree_root, branch_name


def _remove_worktree(workspace_root: Path, worktree_root: Path, branch_name: str) -> None:
    _run_command(["git", "worktree", "remove", "--force", str(worktree_root)], workspace_root)
    _run_command(["git", "branch", "-D", branch_name], workspace_root)


def _merge_worktree(workspace_root: Path, worktree_root: Path) -> None:
    files = _run_command(["git", "status", "--short"], worktree_root)
    if files.returncode != 0:
        raise WorkflowError(f"Unable to inspect worktree changes: {files.stderr.strip()}")
    for line in files.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        source = worktree_root / path
        destination = workspace_root / path
        if source.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


async def _run_worker_task(
    config: RuntimeConfig,
    planner: PlannerDocument,
    task,
    project_description: str,
    semaphore: asyncio.Semaphore,
) -> StepResult:
    async with semaphore:
        _print_stage(config, f"Stage 6/10: worker generation for {task.task_id}")
        allowlist = sorted(set(task.owned_paths + task.required_outputs))
        workspace_before = snapshot_tree(config.workspace_root)
        worktree_root, branch_name = _create_worktree(config.workspace_root, task.task_id)
        try:
            for attempt in range(config.worker_retries + 1):
                try:
                    outcome = await run_codex_exec(
                        worker_prompt(task.role, task, planner.task_summary, project_description, config, worktree_root),
                        config=config,
                        cwd=worktree_root,
                        role=task.role,
                    )
                    step_result = outcome_to_step_result(task.role, outcome)
                    _merge_worktree(config.workspace_root, worktree_root)
                    workspace_after = snapshot_tree(config.workspace_root)
                    created, modified, deleted = diff_snapshots(workspace_before, workspace_after)
                    touched = created + modified
                    enforce_allowlist(touched, deleted, allowlist)
                    step_result.changed_files = touched
                    step_result.deleted_files = deleted
                    step_result.manifest_path = write_stage_manifest(
                        config,
                        f"06_worker_{task.task_id}",
                        {
                            "task": asdict(task),
                            "payload": step_result.payload,
                            "created": created,
                            "modified": modified,
                            "deleted": deleted,
                        },
                    )
                    return step_result
                except WorkflowError as exc:
                    if attempt >= config.worker_retries:
                        raise
                    if "retryable" not in str(exc).lower():
                        raise
                    _print_stage(config, f"Retrying {task.task_id} after infrastructure failure: {exc}")
        finally:
            _remove_worktree(config.workspace_root, worktree_root, branch_name)
    raise WorkflowError(f"Worker task {task.task_id} did not complete")


async def run_workers(
    config: RuntimeConfig,
    planner: PlannerDocument,
    project_description: str,
) -> list[StepResult]:
    semaphore = asyncio.Semaphore(config.max_parallel_workers)
    task_index = {task.task_id: task for task in planner.tasks}
    completed: dict[str, StepResult] = {}
    pending = set(task_index)
    results: list[StepResult] = []
    while pending:
        ready = [
            task_index[task_id]
            for task_id in sorted(pending)
            if all(dependency in completed for dependency in task_index[task_id].dependencies)
        ]
        if not ready:
            raise WorkflowError(f"Dependency deadlock detected among tasks: {sorted(pending)}")
        round_results = await asyncio.gather(
            *[
                _run_worker_task(config, planner, task, project_description, semaphore)
                for task in ready[: config.max_parallel_workers]
            ]
        )
        for result in round_results:
            task_id = str(result.payload.get("task_id"))
            completed[task_id] = result
            pending.remove(task_id)
            results.append(result)
    return results


def validate_artifacts(config: RuntimeConfig, planner: PlannerDocument) -> dict:
    _print_stage(config, "Stage 7/10: artifact validation")
    checks: list[dict] = []
    missing: list[str] = []
    for task in planner.tasks:
        for output in task.required_outputs:
            path = config.workspace_root / output
            if not path.exists():
                missing.append(output)
                checks.append({"path": output, "result": "missing"})
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
            checks.append({"path": output, "result": "present", "bytes": len(content.encode('utf-8'))})
    payload = {"checks": checks, "missing": missing}
    write_stage_manifest(config, "07_artifact_validation", payload)
    if missing:
        raise WorkflowError(f"Missing required outputs: {', '.join(missing)}")
    return payload


def run_local_validation_commands(config: RuntimeConfig, planner: PlannerDocument, label: str, selector: str) -> dict:
    _print_stage(config, f"{label}")
    commands: list[str] = []
    for task in planner.tasks:
        commands.extend(getattr(task, selector))
    executed: list[dict] = []
    if not commands:
        return {"checks": [], "note": "No validation commands were declared in the plan."}
    for command in commands:
        result = subprocess.run(command, cwd=config.workspace_root, shell=True, capture_output=True, text=True, check=False)
        executed.append(
            {
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
            }
        )
        if result.returncode != 0:
            raise WorkflowError(f"Validation command failed: {command}")
    return {"checks": executed}


async def run_verification_agent(
    config: RuntimeConfig,
    project_description: str,
    planner_payload: dict,
    artifacts_summary: dict,
) -> StepResult:
    _print_stage(config, "Stage 9/10: runtime validation")
    outcome = await run_codex_exec(
        verification_prompt(project_description, planner_payload, config, artifacts_summary),
        config=config,
        cwd=config.workspace_root,
        role="Verification Agent",
    )
    result = outcome_to_step_result("Verification Agent", outcome)
    result.manifest_path = write_stage_manifest(config, "09_verification_agent", result.payload)
    return result


async def run_workflow(config: RuntimeConfig) -> dict:
    config.workspace_root = config.workspace_root.resolve()
    config.output_root = (config.workspace_root / config.output_root).resolve()
    ensure_output_dirs(config)
    preflight(config)
    project_description = load_project_description(config)
    context_result = await run_context_analysis(config, project_description)
    planner, planner_result = await run_architect_planner(config, project_description, context_result.payload)
    worker_results = await run_workers(config, planner, project_description)
    artifacts_summary = validate_artifacts(config, planner)
    build_summary = run_local_validation_commands(config, planner, "Stage 8/10: build validation", "build_expectations")
    write_stage_manifest(config, "08_build_validation", build_summary)
    runtime_summary = run_local_validation_commands(config, planner, "Stage 9/10: runtime validation", "runtime_expectations")
    write_stage_manifest(config, "09_runtime_validation", runtime_summary)
    verification = await run_verification_agent(config, project_description, planner_result.payload, artifacts_summary)
    final_payload = {
        "status": "ok",
        "context_analysis": context_result.payload,
        "planner": planner_result.payload,
        "workers": [result.payload for result in worker_results],
        "artifact_validation": artifacts_summary,
        "build_validation": build_summary,
        "runtime_validation": runtime_summary,
        "verification": verification.payload,
    }
    write_stage_manifest(config, "10_final_acceptance_summary", final_payload)
    _print_stage(config, "Stage 10/10: final acceptance summary")
    return final_payload
