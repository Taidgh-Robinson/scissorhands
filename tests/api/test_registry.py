import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scissorhands.api.registry import DuplicateProjectError, ProjectRegistry


class ProjectRegistryTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.database = self.root / "data" / "projects.sqlite3"
        self.first = self.root / "first"
        self.second = self.root / "second"
        self.first.mkdir()
        self.second.mkdir()

    def test_fresh_database_persists_multiple_projects(self) -> None:
        registry = ProjectRegistry(self.database)
        first = registry.add(self.first)
        second = registry.add(self.second, name="Second project")
        reopened = ProjectRegistry(self.database)

        self.assertEqual([project.id for project in reopened.list()], [first.id, second.id])
        self.assertEqual(reopened.get(second.id).name, "Second project")
        self.assertTrue(reopened.get(first.id).available)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)

    def test_duplicate_resolved_folder_and_missing_root(self) -> None:
        registry = ProjectRegistry(self.database)
        registry.add(self.first)
        alias = self.root / "alias"
        alias.symlink_to(self.first, target_is_directory=True)
        with self.assertRaises(DuplicateProjectError):
            registry.add(alias)
        with self.assertRaises(FileNotFoundError):
            registry.add(self.root / "missing")
        self.assertEqual(len(registry.list()), 1)

    def test_missing_project_remains_registered_and_removal_preserves_files(self) -> None:
        registry = ProjectRegistry(self.database)
        project = registry.add(self.first)
        self.first.rmdir()
        self.assertFalse(registry.get(project.id).available)
        self.assertTrue(registry.remove(project.id))
        self.assertFalse(registry.remove(project.id))
        self.assertIsNone(registry.get(project.id))
        self.assertTrue(self.database.exists())

    def test_rejects_future_schema_without_changes(self) -> None:
        self.database.parent.mkdir()
        with sqlite3.connect(self.database) as connection:
            connection.execute("PRAGMA user_version = 99")
        with self.assertRaises(RuntimeError):
            ProjectRegistry(self.database)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 99)
