"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import seed_db  # noqa: E402


@pytest.fixture(scope="session")
def demo_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A freshly seeded demo database with the default seed and as_of date."""
    path = tmp_path_factory.mktemp("data") / "erp_demo.db"
    seed_db.build_database(path)
    return path


@pytest.fixture
def erp_env(demo_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the server at the test database and a temporary audit log; returns the log path."""
    log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("ERP_DB_PATH", str(demo_db))
    monkeypatch.setenv("ERP_AUDIT_LOG", str(log))
    return log
