from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .models import AllowlistViolationError


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_tree(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        relative = file_path.relative_to(root).as_posix()
        if relative.startswith(".git/"):
            continue
        snapshot[relative] = sha256_file(file_path)
    return snapshot


def diff_snapshots(before: dict[str, str], after: dict[str, str]) -> tuple[list[str], list[str], list[str]]:
    created = sorted(set(after) - set(before))
    deleted = sorted(set(before) - set(after))
    modified = sorted(path for path in before.keys() & after.keys() if before[path] != after[path])
    return created, modified, deleted


def enforce_allowlist(
    touched_paths: Iterable[str],
    deleted_paths: Iterable[str],
    allowlist: Iterable[str],
    allow_deletions: bool = False,
) -> None:
    allowed = set(allowlist)
    violations = sorted(path for path in touched_paths if path not in allowed)
    if violations:
        raise AllowlistViolationError(
            f"Worker touched paths outside allowlist: {', '.join(violations)}"
        )
    deleted = list(deleted_paths)
    if deleted and not allow_deletions:
        raise AllowlistViolationError(
            f"Worker deleted files without permission: {', '.join(sorted(deleted))}"
        )


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def dataclass_json(obj: object) -> dict:
    return asdict(obj)
