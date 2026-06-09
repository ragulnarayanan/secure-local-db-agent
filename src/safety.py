"""SQL safety layer: AST-based validation so only safe, read-only SELECT queries
against allowlisted tables ever reach the database.

Why an AST instead of regex: a parser separates SQL *structure* from SQL *text*.
``SELECT * FROM users WHERE name = 'DROP TABLE x'`` is a single harmless SELECT —
the words 'DROP TABLE' are a string literal, not a statement. Regex cannot tell
those apart; the parser can.
"""
from __future__ import annotations

from collections.abc import Iterable

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


class SafetyError(Exception):
    """Base for every rejection. Catch this to treat all safety failures
    uniformly, or catch a subclass for a specific reason."""


class EmptyQueryError(SafetyError):
    """No parseable statement in the input."""


class MultipleStatementsError(SafetyError):
    """More than one statement (the classic '; DROP TABLE' injection shape)."""


class NonSelectError(SafetyError):
    """Statement is not a read-only query (DROP, INSERT, PRAGMA, ATTACH, ...)."""


class UnknownTableError(SafetyError):
    """Query references a table outside the allowlist."""


def validate(sql: str, allowed_tables: Iterable[str]) -> exp.Expression:
    """Validate ``sql`` and return its parsed AST, or raise a ``SafetyError``.

    Checks, in order:
      1. the SQL parses and contains exactly one statement;
      2. that statement is a read-only query (SELECT / UNION / ...);
      3. every referenced real table is in ``allowed_tables`` (case-insensitive),
         ignoring CTE names the query defines for itself.
    """
    try:
        statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except ParseError as e:
        raise SafetyError(f"could not parse SQL: {e}") from e

    if not statements:
        raise EmptyQueryError("no SQL statement found")
    if len(statements) > 1:
        raise MultipleStatementsError(f"expected 1 statement, got {len(statements)}")

    stmt = statements[0]
    if not isinstance(stmt, exp.Query):
        raise NonSelectError(
            f"only read-only SELECT queries are allowed, got {type(stmt).__name__}"
        )

    allowed = {t.lower() for t in allowed_tables}
    # CTE names look like tables to find_all(exp.Table) but aren't real tables.
    cte_names = {c.alias.lower() for c in stmt.find_all(exp.CTE)}
    referenced = {t.name.lower() for t in stmt.find_all(exp.Table)} - cte_names

    unknown = referenced - allowed
    if unknown:
        raise UnknownTableError(
            f"query references tables not in allowlist: {sorted(unknown)}"
        )

    return stmt
