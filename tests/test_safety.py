"""Exhaustive tests for the SQL safety layer.

Covers the guide's required cases plus the edge cases AST validation makes
possible to get right: subquery smuggling, CTE false-positives, UNION, and
case-insensitive table matching.
"""
from __future__ import annotations

import pytest

from src.safety import (
    EmptyQueryError,
    MultipleStatementsError,
    NonSelectError,
    SafetyError,
    UnknownTableError,
    validate,
)

ALLOWED = ["users", "orders"]


# ---- queries that must PASS ------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM users",
        "SELECT id, name FROM users WHERE id = 1",
        "SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id",
        "SELECT COUNT(*) FROM users GROUP BY name HAVING COUNT(*) > 1",
        "SELECT id FROM users UNION SELECT user_id FROM orders",
        "SELECT * FROM (SELECT id FROM users) sub",
        "WITH recent AS (SELECT * FROM orders) SELECT * FROM recent",
    ],
)
def test_valid_selects_pass(sql: str) -> None:
    # validate returns the parsed AST on success (truthy expression)
    assert validate(sql, ALLOWED) is not None


def test_table_match_is_case_insensitive() -> None:
    # SQLite identifiers are case-insensitive; allowlist is "Album", query lowercase.
    assert validate("select * from album", ["Album"]) is not None


def test_string_literal_that_looks_like_ddl_passes() -> None:
    # THE headline case: 'DROP TABLE x' is a string literal, not a statement.
    # Regex would wrongly reject this; the AST sees one harmless SELECT.
    assert validate("SELECT * FROM users WHERE name = 'DROP TABLE x'", ALLOWED)


# ---- queries that must be REJECTED -----------------------------------------


def test_multiple_statements_rejected() -> None:
    with pytest.raises(MultipleStatementsError):
        validate("SELECT * FROM users; DROP TABLE users;", ALLOWED)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE users",
        "DELETE FROM users",
        "UPDATE users SET name = 'x'",
        "INSERT INTO users (name) VALUES ('x')",
        "PRAGMA table_info('users')",
        "ATTACH DATABASE 'evil.db' AS evil",
    ],
)
def test_non_select_rejected(sql: str) -> None:
    with pytest.raises(NonSelectError):
        validate(sql, ALLOWED)


def test_unknown_table_rejected() -> None:
    with pytest.raises(UnknownTableError):
        validate("SELECT * FROM secret_table", ALLOWED)


def test_unknown_table_hidden_in_subquery_rejected() -> None:
    # find_all is recursive, so a forbidden table cannot hide in a subquery.
    with pytest.raises(UnknownTableError):
        validate("SELECT * FROM (SELECT * FROM secret) s", ALLOWED)


def test_unknown_table_hidden_in_cte_rejected() -> None:
    with pytest.raises(UnknownTableError):
        validate("WITH c AS (SELECT * FROM secret) SELECT * FROM c", ALLOWED)


def test_empty_query_rejected() -> None:
    with pytest.raises(EmptyQueryError):
        validate("   ", ALLOWED)


# ---- exception hierarchy ---------------------------------------------------


def test_all_rejections_share_safety_error_base() -> None:
    # A caller can catch SafetyError to handle any rejection uniformly.
    for sql in ["DROP TABLE users", "SELECT * FROM secret", "SELECT 1; SELECT 2;"]:
        with pytest.raises(SafetyError):
            validate(sql, ALLOWED)
