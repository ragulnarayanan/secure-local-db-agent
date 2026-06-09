"""Tests for schema introspection.

We build a small, known SQLite database on disk in a fixture rather than using
the real Chinook file: fast, deterministic, and lets us assert exact values.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.schema import Schema, introspect


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """A tiny two-table DB with a PK, a NOT NULL column, an untyped column,
    and a foreign key — enough to exercise every branch of introspect()."""
    path = tmp_path / "test.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE artists (
            id   INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );
        CREATE TABLE albums (
            id        INTEGER PRIMARY KEY,
            title     TEXT,
            untyped,                       -- column with no declared type
            artist_id INTEGER,
            FOREIGN KEY (artist_id) REFERENCES artists (id)
        );
        """
    )
    conn.commit()
    conn.close()
    return path


def test_introspect_returns_schema(db_path: Path) -> None:
    assert isinstance(introspect(db_path), Schema)


def test_tables_discovered_and_sorted(db_path: Path) -> None:
    schema = introspect(db_path)
    # ORDER BY name -> alphabetical
    assert schema.table_names == ["albums", "artists"]


def test_sqlite_internal_tables_excluded(db_path: Path) -> None:
    # autoincrement would create sqlite_sequence; even without it, assert no
    # sqlite_-prefixed table ever leaks through.
    schema = introspect(db_path)
    assert not any(name.startswith("sqlite_") for name in schema.table_names)


def test_columns_types_and_flags(db_path: Path) -> None:
    schema = introspect(db_path)
    artists = next(t for t in schema.tables if t.name == "artists")

    by_name = {c.name: c for c in artists.columns}
    assert by_name["id"].is_pk is True
    assert by_name["id"].type == "INTEGER"
    assert by_name["name"].not_null is True
    assert by_name["name"].is_pk is False


def test_untyped_column_defaults_to_text(db_path: Path) -> None:
    schema = introspect(db_path)
    albums = next(t for t in schema.tables if t.name == "albums")
    untyped = next(c for c in albums.columns if c.name == "untyped")
    assert untyped.type == "TEXT"


def test_foreign_keys_extracted(db_path: Path) -> None:
    schema = introspect(db_path)
    albums = next(t for t in schema.tables if t.name == "albums")
    assert len(albums.foreign_keys) == 1
    fk = albums.foreign_keys[0]
    assert fk.from_column == "artist_id"
    assert fk.to_table == "artists"
    assert fk.to_column == "id"


def test_table_without_fks_has_empty_list(db_path: Path) -> None:
    schema = introspect(db_path)
    artists = next(t for t in schema.tables if t.name == "artists")
    assert artists.foreign_keys == []


def test_to_prompt_format(db_path: Path) -> None:
    prompt = introspect(db_path).to_prompt()
    assert "Table artists: id INTEGER PK, name TEXT" in prompt
    assert "FK: albums.artist_id -> artists.id" in prompt


def test_missing_db_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        introspect(tmp_path / "does_not_exist.db")
