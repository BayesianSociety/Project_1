from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .models import RuntimeConfig, StepResult, WorkflowError
from .prompts import RESULT_MARKER_BEGIN, RESULT_MARKER_END


@dataclass(slots=True)
class ExecOutcome:
    stdout: str
    stderr: str
    payload: dict


def extract_json_payload(output: str) -> dict:
    start = output.rfind(RESULT_MARKER_BEGIN)
    end = output.rfind(RESULT_MARKER_END)
    if start == -1 or end == -1 or end <= start:
        raise WorkflowError("Missing structured JSON markers in Codex output")
    body = output[start + len(RESULT_MARKER_BEGIN):end].strip()
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"Invalid JSON payload from Codex output: {exc}") from exc


async def _read_stream(stream: asyncio.StreamReader, sink: list[str], printer) -> None:
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            break
        text = chunk.decode("utf-8", errors="replace")
        sink.append(text)
        printer(text)


async def run_codex_exec(
    prompt: str,
    *,
    config: RuntimeConfig,
    cwd: Path,
    role: str,
) -> ExecOutcome:
    env = os.environ.copy()
    env["CODEX_APPROVAL_POLICY"] = config.approval_policy
    env["CODEX_SANDBOX_MODE"] = config.sandbox_mode

    command = [
        "codex",
        "exec",
        "--model",
        config.model,
        "--skip-git-repo-check",
        prompt,
    ]

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []

    def print_stdout(text: str) -> None:
        if config.verbose:
            print(f"[{role}] {text}", end="", flush=True)

    def print_stderr(text: str) -> None:
        if config.verbose:
            print(f"[{role}][stderr] {text}", end="", flush=True)

    stdout_task = asyncio.create_task(_read_stream(process.stdout, stdout_parts, print_stdout))
    stderr_task = asyncio.create_task(_read_stream(process.stderr, stderr_parts, print_stderr))

    try:
        await asyncio.wait_for(process.wait(), timeout=config.step_timeout_seconds)
    except asyncio.TimeoutError as exc:
        process.kill()
        raise WorkflowError(f"{role} timed out after {config.step_timeout_seconds} seconds") from exc

    await asyncio.gather(stdout_task, stderr_task)
    stdout = "".join(stdout_parts)
    stderr = "".join(stderr_parts)
    if process.returncode != 0:
        corruption_signatures = ("broken pipe", "unexpected EOF", "connection reset", "transport closed")
        if any(signature in (stdout + stderr).lower() for signature in corruption_signatures):
            raise WorkflowError(f"{role} failed with retryable Codex runtime corruption")
        raise WorkflowError(f"{role} failed with exit code {process.returncode}")

    payload = extract_json_payload(stdout)
    return ExecOutcome(stdout=stdout, stderr=stderr, payload=payload)


def outcome_to_step_result(role: str, outcome: ExecOutcome) -> StepResult:
    return StepResult(
        role=role,
        status=str(outcome.payload.get("status", "unknown")),
        message=str(outcome.payload.get("summary", "")),
        payload=outcome.payload,
        stdout=outcome.stdout,
        stderr=outcome.stderr,
        changed_files=list(outcome.payload.get("changed_files", [])),
    )
