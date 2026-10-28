"""Read-only access to the ERP SQLite database."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "erp_demo.db"


def db_path() -> Path:
    """Database location: ``ERP_DB_PATH`` env var, else ``data/erp_demo.db`` in the project."""
    return Path(os.environ.get("ERP_DB_PATH", DEFAULT_DB_PATH)).resolve()


def connect_readonly(path: Path | None = None) -> sqlite3.Connection:
    """Open the database so that no statement can modify it.

    Two independent guards: the file is opened with ``mode=ro`` (SQLite refuses
    writes at the file level) and ``PRAGMA query_only`` rejects write statements.
    """
    path = (path or db_path()).resolve()
    if not path.exists():
        raise FileNotFoundError(
            f"Database not found at {path}. Create it with: python scripts/seed_db.py"
        )
    con = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    return con
