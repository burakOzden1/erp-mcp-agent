"""Audit trail: one JSON line per tool call."""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from erp_mcp.db import PROJECT_ROOT

DEFAULT_LOG_PATH = PROJECT_ROOT / "logs" / "audit.jsonl"

_lock = threading.Lock()


def log_path() -> Path:
    """Log location: ``ERP_AUDIT_LOG`` env var, else ``logs/audit.jsonl`` in the project."""
    return Path(os.environ.get("ERP_AUDIT_LOG", DEFAULT_LOG_PATH))


def log_call(
    tool: str,
    params: dict[str, Any],
    *,
    row_count: int,
    duration_ms: float,
    status: str = "ok",
    error: str | None = None,
) -> dict[str, Any]:
    """Append one audit record and return it."""
    record: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "tool": tool,
        "params": params,
        "row_count": row_count,
        "duration_ms": round(duration_ms, 2),
        "status": status,
    }
    if error:
        record["error"] = error
    path = log_path()
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return record
