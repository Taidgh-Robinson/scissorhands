"""Persistent registry of project folders visible to the reporting API."""

from __future__ import annotations

import os
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

SCHEMA_VERSION = 1


class DuplicateProjectError(ValueError):
    """The resolved folder is already registered."""


@dataclass(frozen=True, slots=True)
class Project:
    id: str
    name: str
    root: Path
    created_at: str

    @property
    def available(self) -> bool:
        return (
            self.root.is_dir()
            and not self.root.is_symlink()
            and not (self.root / ".scissorhands").is_symlink()
        )


def default_registry_path() -> Path:
    """Choose user data storage; callers can override this for other instances."""
    configured = os.environ.get("SCISSORHANDS_REGISTRY_DB")
    if configured:
        return Path(configured).expanduser()
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "scissorhands" / "projects.sqlite3"


class ProjectRegistry:
    """SQLite connections are short lived so concurrent requests can use the registry."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def _migrate(self) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version > SCHEMA_VERSION:
                    raise RuntimeError(f"Unsupported project registry version: {version}")
                if version < 1:
                    connection.execute(
                        """CREATE TABLE projects (
                            id TEXT PRIMARY KEY,
                            name TEXT NOT NULL,
                            root TEXT NOT NULL UNIQUE,
                            created_at TEXT NOT NULL
                        )"""
                    )
                    connection.execute("PRAGMA user_version = 1")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def add(self, root: Path, *, name: str | None = None) -> Project:
        resolved = root.expanduser().resolve(strict=True)
        if not resolved.is_dir():
            raise ValueError(f"Project root is not a directory: {resolved}")
        project_name = (resolved.name if name is None else name).strip()
        if not project_name:
            raise ValueError("Project name must not be empty")
        project = Project(str(uuid4()), project_name, resolved, datetime.now(UTC).isoformat())
        with self._connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO projects (id, name, root, created_at) VALUES (?, ?, ?, ?)",
                    (project.id, project.name, str(project.root), project.created_at),
                )
                connection.commit()
            except sqlite3.IntegrityError as error:
                raise DuplicateProjectError(f"Project already registered: {resolved}") from error
        return project

    def list(self) -> tuple[Project, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id, name, root, created_at FROM projects ORDER BY created_at, id"
            ).fetchall()
        return tuple(_project(row) for row in rows)

    def get(self, project_id: str) -> Project | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id, name, root, created_at FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return _project(row) if row is not None else None

    def remove(self, project_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            connection.commit()
        return cursor.rowcount != 0


def _project(row: sqlite3.Row) -> Project:
    return Project(row["id"], row["name"], Path(row["root"]), row["created_at"])
