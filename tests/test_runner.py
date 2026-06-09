"""Tests for the orchestrator.

A FakeAgent stands in for OllamaAgent so these run without a model and exercise
each pipeline branch (ok / safety reject / execution error / generation error).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import requests

from src.agent import SQLResponse
from src.runner import Runner, execute_readonly


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "shop.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL);
        INSERT INTO users VALUES (1, 'Ada'), (2, 'Lin');
        INSERT INTO orders VALUES (1, 1, 9.99), (2, 1, 5.00);
        """
    )
    conn.commit()
    conn.close()
    return path


class FakeAgent:
    """Returns canned SQL, or raises, without touching the network."""

    def __init__(self, sql: str = "", reasoning: str = "r", raises: Exception | None = None):
        self._sql = sql
        self._reasoning = reasoning
        self._raises = raises

    def generate_sql(self, schema_text: str, question: str) -> SQLResponse:
        if self._raises is not None:
            raise self._raises
        return SQLResponse(sql=self._sql, reasoning=self._reasoning)


def test_run_ok_returns_rows(db_path: Path) -> None:
    runner = Runner(db_path, FakeAgent(sql="SELECT name FROM users"))
    res = runner.run("names?")
    assert res.ok is True
    assert res.failure_reason is None
    assert res.columns == ["name"]
    assert set(res.rows) == {("Ada",), ("Lin",)}
    assert res.latency_ms >= 0


def test_run_rejects_non_select(db_path: Path) -> None:
    runner = Runner(db_path, FakeAgent(sql="DROP TABLE users"))
    res = runner.run("drop it")
    assert res.ok is False
    assert res.failure_reason.startswith("safety")
    assert res.sql == "DROP TABLE users"  # captured for the audit trail


def test_run_rejects_unknown_table(db_path: Path) -> None:
    runner = Runner(db_path, FakeAgent(sql="SELECT * FROM secret"))
    res = runner.run("peek")
    assert res.ok is False
    assert "UnknownTableError" in res.failure_reason


def test_run_reports_execution_error(db_path: Path) -> None:
    # Passes safety (users is allowed) but the column doesn't exist.
    runner = Runner(db_path, FakeAgent(sql="SELECT nope FROM users"))
    res = runner.run("bad column")
    assert res.ok is False
    assert res.failure_reason.startswith("execution")


def test_run_reports_generation_error(db_path: Path) -> None:
    runner = Runner(db_path, FakeAgent(raises=requests.ConnectionError("down")))
    res = runner.run("anything")
    assert res.ok is False
    assert res.failure_reason.startswith("generation")
    assert res.sql is None


def test_execute_readonly_blocks_writes(db_path: Path) -> None:
    # Defense in depth: even bypassing safety, the connection itself is read-only.
    with pytest.raises(sqlite3.OperationalError):
        execute_readonly(db_path, "INSERT INTO users VALUES (3, 'Eve')")
