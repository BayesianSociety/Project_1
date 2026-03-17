# Codex Multi-Agent Workflow

This repository contains a Codex-only multi-agent orchestrator written in Python 3.10. It reads `Project_description.md` as the canonical brief, creates a typed plan, runs bounded concurrent `codex exec` workers in isolated git worktrees, enforces per-step filesystem allowlists, and writes stage manifests with provenance data.

## What It Does

The workflow is phase-based and explicit:

1. Environment preflight
2. Context analysis
3. Planner generation
4. Planner schema validation
5. Planner repair loop
6. Worker generation
7. Artifact validation
8. Build validation
9. Runtime validation
10. Final acceptance summary

The execution roles are:

- `Orchestrator`
- `Context Analyst`
- `Architect`
- `Backend Producer`
- `Frontend Producer`
- `Verification Agent`

## Requirements

- Python 3.10+
- `codex` CLI installed and authenticated via `codex login`
- `git`

The workflow fails fast if `Project_description.md` is missing.

## Install

```bash
python3 -m pip install -e .
```

## Run

Create `Project_description.md` in the repository root, then run:

```bash
codex-multi-agent --workspace-root .
```

Useful flags:

- `--model gpt-5-codex`
- `--max-parallel-workers 2`
- `--timeout-seconds 1800`
- `--output-root .codex_multi_agent`
- `--quiet`

## Outputs

The workflow writes artifacts under `.codex_multi_agent/`:

- `plans/planner.json`
- `manifests/*.json`

Each stage manifest captures the structured result for that stage. Worker manifests include touched files and allowlist enforcement evidence.

## Notes

- Worker edits are isolated in git worktrees under `/tmp/codex_multi_agent_worktrees`.
- Build and runtime validation commands come from the Architect plan and run locally in the main workspace.
- The Verification Agent performs an additional semantic review of the resulting artifacts against the plan and project brief.
