"""Orchestrator: question -> LLM -> safety -> execute -> result.

Ties together schema (Day 1), agent (Day 2), and safety (Day 3) into one call.
The schema is introspected once per Runner and reused for every question.
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

import requests
from pydantic import ValidationError

from src.agent import OllamaAgent
from src.safety import SafetyError, validate
from src.schema import introspect


@dataclass
class RunResult:
    """Everything the UI / eval needs about one question's run."""

    question: str
    sql: str | None = None
    reasoning: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    latency_ms: float = 0.0  # LLM generation time, the metric the eval reports
    ok: bool = False
    failure_reason: str | None = None  # which stage failed, for eval analysis


def execute_readonly(db_path: str | Path, sql: str) -> tuple[list[str], list[tuple]]:
    """Run a query against a read-only connection; return (columns, rows).

    Read-only mode is defense in depth: safety.validate already guarantees a
    SELECT, but opening with mode=ro means even a bug can't mutate the DB.
    """
    uri = f"file:{Path(db_path)}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        return columns, cur.fetchall()


class Runner:
    def __init__(self, db_path: str | Path, agent: OllamaAgent) -> None:
        self.db_path = Path(db_path)
        self.agent = agent
        self.schema = introspect(self.db_path)
        self._schema_prompt = self.schema.to_prompt()
        self._allowed = self.schema.table_names

    def run(self, question: str) -> RunResult:
        result = RunResult(question=question)

        # 1. Generate SQL (timed — this is the inference latency we benchmark).
        start = time.perf_counter()
        try:
            response = self.agent.generate_sql(self._schema_prompt, question)
        except (requests.RequestException, ValidationError) as e:
            result.failure_reason = f"generation: {type(e).__name__}"
            return result
        finally:
            result.latency_ms = (time.perf_counter() - start) * 1000

        result.sql = response.sql
        result.reasoning = response.reasoning

        # 2. Safety gate.
        try:
            validate(response.sql, self._allowed)
        except SafetyError as e:
            result.failure_reason = f"safety: {type(e).__name__}: {e}"
            return result

        # 3. Execute.
        try:
            result.columns, result.rows = execute_readonly(self.db_path, response.sql)
        except sqlite3.Error as e:
            result.failure_reason = f"execution: {type(e).__name__}: {e}"
            return result

        result.ok = True
        return result
