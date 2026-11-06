"""Read persisted runs for one project without starting agents or writing files."""

from __future__ import annotations

import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from scissorhands.core.work_items import validate_work_item_id

ArtifactState = Literal[
    "available", "missing", "invalid", "unavailable", "unsafe", "too_large"
]
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_TEXT_BYTES = 1024 * 1024
DEFAULT_TEXT_BYTES = 64 * 1024

# Callers select a kind, never a filename supplied by an artifact or HTTP client.
_RUN_ARTIFACTS = {
    "manifest": "report.json",
    "settings": "run.json",
    "work_item": "work-item.json",
    "work_item_toml": "work-item.toml",
    "report": "report.md",
    "patch": "changes.patch",
}
_LOOP_ARTIFACTS = {
    "receipt": "iteration-{number}.json",
    "report": "iteration-{number}.md",
    "agent_output": "iteration-{number}.log",
    "final_message": "iteration-{number}.final.txt",
    "status": "status.json",
    "progress": "progress.md",
    "prompt": "prompt.md",
    "patch": "changes.patch",
    "verification_output": "verification-{verification}.log",
}


class UnsafeArtifactPath(ValueError):
    """A storage directory or artifact escapes its permitted location."""


@dataclass(frozen=True, slots=True)
class Artifact:
    """JSON objects or bounded UTF-8 text, with explicit availability.

    Text offsets and lengths are bytes. A split UTF-8 character is replaced.
    Truncation means bytes were omitted before or after this text window.
    """

    state: ArtifactState
    data: dict[str, object] | str | None = None
    offset: int = 0
    bytes_read: int = 0
    total_bytes: int | None = None
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class RunSummary:
    work_item_id: str
    run_id: str
    state: str
    outcome: str | None
    started_at: str | None
    finished_at: str | None
    manifest_state: ArtifactState


@dataclass(frozen=True, slots=True)
class RunDetail:
    summary: RunSummary
    manifest: Artifact
    settings: Artifact
    work_item: Artifact
    loops: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class LoopDetail:
    work_item_id: str
    run_id: str
    number: int
    receipt: Artifact


def _positive_integer(value: int, name: str) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _directory(path: Path) -> Path:
    # Reject directory aliases, including aliases into another run in this project.
    if path.is_symlink():
        raise UnsafeArtifactPath(f"Symlinked storage directory: {path.name}")
    if not path.is_dir():
        raise FileNotFoundError(f"Storage directory not found: {path}")
    return path


class RunRepository:
    """Synchronous, framework-independent queries scoped to an explicit root.

    A project without .scissorhands has empty listings. A missing project raises
    FileNotFoundError. Storage directory symlinks are rejected; file symlinks may
    resolve within the selected run. No manifest-provided paths are followed.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def _storage(self) -> Path:
        _directory(self.root)
        return _directory(self.root / ".scissorhands")

    def _item(self, work_item_id: str) -> Path:
        validate_work_item_id(work_item_id)
        return _directory(self._storage() / work_item_id)

    def _run(self, work_item_id: str, run_id: str) -> Path:
        if not isinstance(run_id, str) or not re.fullmatch(r"run-[0-9]+", run_id):
            raise ValueError("run_id must be a numbered run directory")
        return _directory(self._item(work_item_id) / run_id)

    def list_work_items(self) -> tuple[str, ...]:
        """List valid work-item directories; ignore unrelated entries and aliases."""
        _directory(self.root)
        try:
            storage = self._storage()
        except FileNotFoundError:
            return ()
        items = []
        for child in storage.iterdir():
            try:
                validate_work_item_id(child.name)
                _directory(child)
            except (ValueError, OSError):
                continue
            items.append(child.name)
        return tuple(sorted(items))

    def list_runs(self, work_item_id: str | None = None) -> tuple[RunSummary, ...]:
        """List runs by work item and numeric run order, including damaged runs."""
        items = self.list_work_items() if work_item_id is None else (work_item_id,)
        summaries = []
        for item in items:
            item_dir = self._item(item)
            runs = []
            for child in item_dir.iterdir():
                if not re.fullmatch(r"run-[0-9]+", child.name):
                    continue
                try:
                    _directory(child)
                except (ValueError, OSError):
                    continue
                runs.append(child.name)
            for run_id in sorted(runs, key=lambda name: (int(name[4:]), name)):
                manifest = self.read_artifact(item, run_id, "manifest")
                summaries.append(self._summary(item, run_id, manifest))
        return tuple(summaries)

    @staticmethod
    def _summary(work_item_id: str, run_id: str, manifest: Artifact) -> RunSummary:
        data = manifest.data if isinstance(manifest.data, dict) else {}

        def text(key: str) -> str | None:
            value = data.get(key)
            return value if isinstance(value, str) else None

        state = text("state")
        if state not in {"queued", "running", "finished", "cancelled", "interrupted"}:
            state = "unknown"
        return RunSummary(
            work_item_id,
            run_id,
            state,
            text("outcome"),
            text("started_at"),
            text("finished_at"),
            manifest.state,
        )

    def read_run(self, work_item_id: str, run_id: str) -> RunDetail:
        run = self._run(work_item_id, run_id)
        loops = []
        for child in run.iterdir():
            match = re.fullmatch(r"loop-([0-9]+)", child.name)
            if match is None:
                continue
            number = int(match[1])
            if number < 1 or child.name != f"loop-{number:04d}":
                continue
            try:
                _directory(child)
            except (ValueError, OSError):
                continue
            loops.append(number)
        manifest = self.read_artifact(work_item_id, run_id, "manifest")
        return RunDetail(
            self._summary(work_item_id, run_id, manifest),
            manifest,
            self.read_artifact(work_item_id, run_id, "settings"),
            self.read_artifact(work_item_id, run_id, "work_item"),
            tuple(sorted(loops)),
        )

    def read_loop(self, work_item_id: str, run_id: str, number: int) -> LoopDetail:
        return LoopDetail(
            work_item_id,
            run_id,
            number,
            self.read_artifact(work_item_id, run_id, "receipt", loop=number),
        )

    def read_artifact(
        self,
        work_item_id: str,
        run_id: str,
        kind: str,
        *,
        loop: int | None = None,
        verification: int | None = None,
        offset: int = 0,
        limit: int = DEFAULT_TEXT_BYTES,
        tail: bool = False,
    ) -> Artifact:
        """Read a known artifact. JSON is capped; text supports byte windows/tails.

        Missing run/loop directories raise FileNotFoundError. Missing or damaged
        files return an Artifact state so partial runs remain inspectable.
        """
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be a non-negative integer")
        _positive_integer(limit, "limit")
        if limit > MAX_TEXT_BYTES:
            raise ValueError(f"limit must be at most {MAX_TEXT_BYTES}")
        if tail and offset:
            raise ValueError("tail and offset cannot be combined")
        if verification is not None and (kind != "verification_output" or loop is None):
            raise ValueError("verification is only valid for loop verification output")
        kinds = _RUN_ARTIFACTS if loop is None else _LOOP_ARTIFACTS
        if kind not in kinds:
            raise ValueError(f"Unknown artifact kind: {kind}")
        if kind == "verification_output":
            _positive_integer(verification, "verification")
        run = self._run(work_item_id, run_id)
        directory = run
        if loop is not None:
            _positive_integer(loop, "loop")
            directory = _directory(run / f"loop-{loop:04d}")
        path = directory / kinds[kind].format(number=loop, verification=verification)
        is_json = path.suffix == ".json"
        if is_json and (offset or tail):
            raise ValueError("JSON artifacts do not support offset or tail")
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(run):
                return Artifact("unsafe")
            if not stat.S_ISREG(resolved.stat().st_mode):
                return Artifact("unavailable")
            with resolved.open("rb") as source:
                size = source.seek(0, 2)
                start = max(0, size - limit) if tail else min(offset, size)
                source.seek(0 if is_json else start)
                content = source.read(MAX_JSON_BYTES + 1 if is_json else limit)
        except FileNotFoundError:
            return Artifact("missing")
        except (OSError, RuntimeError):
            return Artifact("unavailable")
        if is_json:
            if len(content) > MAX_JSON_BYTES:
                return Artifact("too_large", total_bytes=size)
            try:
                data = json.loads(content)
            except (ValueError, UnicodeError, RecursionError):
                return Artifact("invalid", total_bytes=size)
            if not isinstance(data, dict):
                return Artifact("invalid", total_bytes=size)
            return Artifact(
                "available", data, bytes_read=len(content), total_bytes=size
            )
        return Artifact(
            "available",
            content.decode("utf-8", errors="replace"),
            start,
            len(content),
            size,
            start > 0 or start + len(content) < size,
        )
