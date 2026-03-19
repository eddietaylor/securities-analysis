from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


REGISTRY_DIR = Path("artifacts") / "registry"
REGISTRY_PATH = REGISTRY_DIR / "run_registry.jsonl"


def new_run_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}_{uuid4().hex[:8]}"


def write_run_manifest(
    artifact_dir: str | Path,
    *,
    kind: str,
    run_id: str,
    summary: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    artifact_path = Path(artifact_dir)
    artifact_path.mkdir(parents=True, exist_ok=True)
    manifest_path = artifact_path / "run_manifest.json"
    payload = {
        "run_id": run_id,
        "kind": kind,
        "created_at": datetime.now(UTC).isoformat(),
        "artifact_dir": str(artifact_path),
        "summary": summary or {},
        "config": config or {},
        "extra": extra or {},
    }
    manifest_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    append_run_registry(payload)
    return manifest_path


def append_run_registry(payload: dict[str, Any]) -> None:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    with REGISTRY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str))
        handle.write("\n")
