"""Run manifest audit package utilities for MINOS-CORE pipelines."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

RUN_MANIFEST_SCHEMA_VERSION = "minos-core.run_manifest.v1"


JsonObject = dict[str, Any]
ArtifactLike = str | Path | bytes | bytearray | memoryview | JsonObject | list[Any]


def sha256_bytes(data: bytes | bytearray | memoryview) -> str:
    """Return the SHA-256 hex digest for raw bytes."""

    return hashlib.sha256(bytes(data)).hexdigest()


def sha256_json(payload: Any) -> str:
    """Return a deterministic SHA-256 hex digest for a JSON-serializable value."""

    return sha256_bytes(_canonical_json_bytes(payload))


def sha256_file(path: str | Path) -> str:
    """Return the SHA-256 hex digest for the exact bytes stored at ``path``."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_sha256(artifact: ArtifactLike) -> str:
    """Hash JSON-like artifacts, file paths, or raw bytes with SHA-256."""

    if isinstance(artifact, (bytes, bytearray, memoryview)):
        return sha256_bytes(artifact)
    if isinstance(artifact, (dict, list)):
        return sha256_json(artifact)
    return sha256_file(artifact)


def write_run_manifest(path: str | Path, manifest: JsonObject) -> Path:
    """Write a run manifest JSON file and return its destination path."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return destination


def build_run_manifest(
    *,
    run_id: str | None = None,
    created_at: str | None = None,
    inputs: Any = None,
    outputs: Any = None,
    stage_results: Any = None,
    quality_gates: Any = None,
    review_confirmations: Any = None,
    artifact_hashes: dict[str, str] | None = None,
    artifacts: dict[str, ArtifactLike] | None = None,
    warnings: Any = None,
    schema_version: str = RUN_MANIFEST_SCHEMA_VERSION,
) -> JsonObject:
    """Build a JSON-serializable run manifest audit package.

    ``artifact_hashes`` can be supplied directly. ``artifacts`` hashes JSON-like
    payloads, file paths, or raw bytes and merges those digests into
    ``artifact_hashes``.
    """

    resolved_hashes = dict(artifact_hashes or {})
    for name, artifact in (artifacts or {}).items():
        resolved_hashes[name] = artifact_sha256(artifact)

    stage_entries = _dump_json_value(stage_results, default=[])

    return {
        "document_type": "run_manifest",
        "schema_version": schema_version,
        "run_id": run_id or _new_run_id(),
        "created_at": created_at or _utc_now_iso(),
        "inputs": _dump_json_object(inputs),
        "outputs": _dump_json_object(outputs),
        "stages": stage_entries,
        "stage_results": stage_entries,
        "quality_gates": _dump_json_value(quality_gates, default=[]),
        "review_confirmations": _dump_json_value(review_confirmations, default=[]),
        "artifact_hashes": resolved_hashes,
        "warnings": _dump_json_value(warnings, default=[]),
    }


def _new_run_id() -> str:
    return f"run-{uuid4()}"


def _utc_now_iso() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        _dump_json_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _dump_json_object(value: Any) -> JsonObject:
    dumped = _dump_json_value(value, default={})
    if isinstance(dumped, dict):
        return dumped
    return {"value": dumped}


def _dump_json_value(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {str(key): _dump_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_dump_json_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dict__"):
        return {
            str(key): _dump_json_value(item) for key, item in value.__dict__.items()
        }
    return value
