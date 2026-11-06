"""Read-only application queries over one project's persisted runs."""

from __future__ import annotations

from pathlib import Path

from scissorhands.storage.artifacts import (
    DEFAULT_TEXT_BYTES,
    ReadWindow,
    artifact_filename,
    read_artifact_file,
)
from scissorhands.storage.models import Artifact, LoopDetail, RunDetail, RunSummary
from scissorhands.storage.paths import ProjectLayout


class RunRepository:
    """Read run history without invoking agents or mutating the project.

    Directory discovery, file safety, and decoding live in the storage helpers;
    this class assembles the results consumed by application interfaces.
    """

    def __init__(self, root: Path) -> None:
        self._layout = ProjectLayout(root)
        self.root = self._layout.root

    def list_work_items(self) -> tuple[str, ...]:
        """Return valid work-item IDs in alphabetical order."""
        return self._layout.list_work_item_ids()

    def list_runs(self, work_item_id: str | None = None) -> tuple[RunSummary, ...]:
        """List runs in numeric order, retaining runs with damaged manifests."""
        items = self.list_work_items() if work_item_id is None else (work_item_id,)
        summaries = []
        for item in items:
            for run_id in self._layout.list_run_ids(item):
                manifest = self.read_artifact(item, run_id, "manifest")
                summaries.append(_summarize_run(item, run_id, manifest))
        return tuple(summaries)

    def read_run(self, work_item_id: str, run_id: str) -> RunDetail:
        """Read persisted metadata and discover loops, including unfinished ones."""
        run = self._layout.run_directory(work_item_id, run_id)
        manifest = self.read_artifact(work_item_id, run_id, "manifest")
        return RunDetail(
            summary=_summarize_run(work_item_id, run_id, manifest),
            manifest=manifest,
            settings=self.read_artifact(work_item_id, run_id, "settings"),
            work_item=self.read_artifact(work_item_id, run_id, "work_item"),
            loops=self._layout.list_loop_numbers(run),
        )

    def read_loop(self, work_item_id: str, run_id: str, number: int) -> LoopDetail:
        """Read the harness receipt without changing the agent's claims."""
        receipt = self.read_artifact(work_item_id, run_id, "receipt", loop=number)
        return LoopDetail(
            work_item_id=work_item_id, run_id=run_id, number=number, receipt=receipt
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
        """Read a known artifact with bounded JSON or a byte window of text.

        Missing directories raise FileNotFoundError. Missing or damaged files
        return an explicit availability state so partial runs remain readable.
        """
        window = ReadWindow(offset=offset, limit=limit, tail=tail)
        filename = artifact_filename(kind, loop, verification)
        run = self._layout.run_directory(work_item_id, run_id)
        directory = run if loop is None else self._layout.loop_directory(run, loop)
        return read_artifact_file(directory / filename, run, window)


def _summarize_run(work_item_id: str, run_id: str, manifest: Artifact) -> RunSummary:
    data = manifest.data if isinstance(manifest.data, dict) else {}
    state = _text_field(data, "state")
    if state not in {"queued", "running", "finished", "cancelled", "interrupted"}:
        state = "unknown"
    return RunSummary(
        work_item_id=work_item_id,
        run_id=run_id,
        state=state,
        outcome=_text_field(data, "outcome"),
        started_at=_text_field(data, "started_at"),
        finished_at=_text_field(data, "finished_at"),
        manifest_state=manifest.state,
    )


def _text_field(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) else None
