"""Schema introspection for SQLite databases.

Reads tables, columns, types, primary keys, and foreign keys out of any SQLite
file and formats them into a compact, prompt-ready string for the LLM.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Column:
    """One column in a table."""
    name: str
    type: str
    is_pk: bool = False
    not_null: bool = False


@dataclass
class ForeignKey:
    """A foreign-key relationship: this table's `from_column` references
    `to_table.to_column`."""
    from_column: str
    to_table: str
    to_column: str


@dataclass
class Table:
    name: str
    columns: list[Column] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)


@dataclass
class Schema:
    tables: list[Table] = field(default_factory=list)

    @property
    def table_names(self) -> list[str]:
        """Names of all tables — this is what the Day 3 safety allowlist consumes."""
        return [t.name for t in self.tables]

    def to_prompt(self) -> str:
        """Format the schema as a compact, token-efficient string for the LLM.

        One line per table; foreign keys called out explicitly so the model
        knows how to JOIN.
        """
        lines: list[str] = []
        for t in self.tables:
            cols = [f"{c.name} {c.type}{' PK' if c.is_pk else ''}" for c in t.columns]
            lines.append(f"Table {t.name}: {', '.join(cols)}")
            for fk in t.foreign_keys:
                lines.append(
                    f"  FK: {t.name}.{fk.from_column} -> {fk.to_table}.{fk.to_column}"
                )
        return "\n".join(lines)


def introspect(db_path: str | Path) -> Schema:
    """Read a SQLite file and return its full schema (tables, columns, FKs)."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    schema = Schema()
    with closing(sqlite3.connect(db_path)) as conn:
        # User tables only — skip SQLite's internal bookkeeping (sqlite_master, etc.).
        # Materialize the names first so we're not iterating one cursor while we
        # open PRAGMA cursors inside the loop.
        table_names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            ).fetchall()
        ]

        for tname in table_names:
            table = Table(name=tname)

            # PRAGMA table_info row: (cid, name, type, notnull, dflt_value, pk)
            for row in conn.execute(f"PRAGMA table_info('{tname}')").fetchall():
                table.columns.append(
                    Column(
                        name=row[1],
                        type=row[2] or "TEXT",
                        not_null=bool(row[3]),
                        is_pk=bool(row[5]),
                    )
                )

            # PRAGMA foreign_key_list row: (id, seq, table, from, to, on_update, ...)
            for row in conn.execute(f"PRAGMA foreign_key_list('{tname}')").fetchall():
                table.foreign_keys.append(
                    ForeignKey(
                        from_column=row[3],
                        to_table=row[2],
                        to_column=row[4],
                    )
                )

            schema.tables.append(table)

    return schema


if __name__ == "__main__":
    import sys

    db = sys.argv[1] if len(sys.argv) > 1 else "data/chinook.db"
    s = introspect(db)
    print(f"Found {len(s.tables)} tables: {', '.join(s.table_names)}\n")
    print(s.to_prompt())
