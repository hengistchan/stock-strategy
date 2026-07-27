from __future__ import annotations

import sqlite3
from pathlib import Path

STATE_SCHEMA_VERSION = 3


def connect_database(database_path: Path) -> sqlite3.Connection:
    """Open the shared workspace database with the project's safety settings."""
    connection = sqlite3.connect(
        database_path.resolve(),
        timeout=5,
        isolation_level="DEFERRED",
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def initialize_repository_metadata(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS repository_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO repository_metadata(key, value)
        VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(STATE_SCHEMA_VERSION),),
    )
