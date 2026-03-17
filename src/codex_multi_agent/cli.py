from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .models import PreflightError, RuntimeConfig, WorkflowError
from .orchestrator import run_workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex-only multi-agent workflow runner")
    parser.add_argument("--workspace-root", default=".", help="Repository root")
    parser.add_argument("--output-root", default=".codex_multi_agent", help="Directory for manifests and logs")
    parser.add_argument("--project-description", default="Project_description.md", help="Canonical project brief path")
    parser.add_argument("--model", default="gpt-5-codex", help="Codex model name")
    parser.add_argument("--max-parallel-workers", type=int, default=2, help="Concurrency limit for worker roles")
    parser.add_argument("--planner-repair-attempts", type=int, default=2, help="Planner repair attempts")
    parser.add_argument("--worker-retries", type=int, default=2, help="Retry count for retryable worker failures")
    parser.add_argument("--timeout-seconds", type=int, default=1800, help="Per-step timeout")
    parser.add_argument("--approval-policy", default="never", help="Codex approval policy")
    parser.add_argument("--sandbox-mode", default="workspace-write", help="Codex sandbox mode")
    parser.add_argument("--quiet", action="store_true", help="Reduce stage logging")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = RuntimeConfig(
        model=args.model,
        sandbox_mode=args.sandbox_mode,
        approval_policy=args.approval_policy,
        workspace_root=Path(args.workspace_root),
        output_root=Path(args.output_root),
        project_description=args.project_description,
        max_parallel_workers=args.max_parallel_workers,
        planner_repair_attempts=args.planner_repair_attempts,
        worker_retries=args.worker_retries,
        step_timeout_seconds=args.timeout_seconds,
        verbose=not args.quiet,
    )

    try:
        payload = asyncio.run(run_workflow(config))
    except PreflightError as exc:
        print(json.dumps({"status": "preflight_failed", "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    except WorkflowError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
