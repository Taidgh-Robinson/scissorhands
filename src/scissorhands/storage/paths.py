"""Project layout, directory discovery, and storage path validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from scissorhands.core.work_items import validate_work_item_id


class UnsafeArtifactPath(ValueError):
    """A storage directory is an alias outside its permitted location."""


def require_positive_integer(value: object, name: str) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def require_directory(path: Path) -> Path:
    """Reject directory aliases, including aliases into another run."""
    if path.is_symlink():
        raise UnsafeArtifactPath(f"Symlinked storage directory: {path.name}")
    if not path.is_dir():
        raise FileNotFoundError(f"Storage directory not found: {path}")
    return path


def _is_storage_directory(path: Path) -> bool:
    try:
        require_directory(path)
    except (ValueError, OSError):
        return False
    return True


@dataclass(frozen=True, slots=True)
class RunPaths:
    run_dir: Path
    started_at: str

    def loop_dir(self, number: int) -> Path:
        return self.run_dir / f"loop-{number:04d}"


class ProjectLayout:
    """Resolve IDs beneath one explicit root; discovery never creates files."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def storage_directory(self) -> Path:
        require_directory(self.root)
        return require_directory(self.root / ".scissorhands")

    def work_item_directory(self, work_item_id: str) -> Path:
        validate_work_item_id(work_item_id)
        return require_directory(self.storage_directory() / work_item_id)

    def run_directory(self, work_item_id: str, run_id: str) -> Path:
        if not isinstance(run_id, str) or not re.fullmatch(r"run-[0-9]+", run_id):
            raise ValueError("run_id must be a numbered run directory")
        return require_directory(self.work_item_directory(work_item_id) / run_id)

    def loop_directory(self, run: Path, number: int) -> Path:
        require_positive_integer(number, "loop")
        return require_directory(run / f"loop-{number:04d}")

    def list_work_item_ids(self) -> tuple[str, ...]:
        require_directory(self.root)
        try:
            storage = self.storage_directory()
        except FileNotFoundError:
            return ()
        items = []
        for child in storage.iterdir():
            try:
                validate_work_item_id(child.name)
            except ValueError:
                continue
            if _is_storage_directory(child):
                items.append(child.name)
        return tuple(sorted(items))

    def list_run_ids(self, work_item_id: str) -> tuple[str, ...]:
        directory = self.work_item_directory(work_item_id)
        runs = [
            child.name
            for child in directory.iterdir()
            if re.fullmatch(r"run-[0-9]+", child.name) and _is_storage_directory(child)
        ]
        return tuple(sorted(runs, key=lambda name: (int(name[4:]), name)))

    def list_loop_numbers(self, run: Path) -> tuple[int, ...]:
        numbers = []
        for child in run.iterdir():
            match = re.fullmatch(r"loop-([0-9]+)", child.name)
            if match is None:
                continue
            number = int(match[1])
            if number < 1 or child.name != f"loop-{number:04d}":
                continue
            if _is_storage_directory(child):
                numbers.append(number)
        return tuple(sorted(numbers))
