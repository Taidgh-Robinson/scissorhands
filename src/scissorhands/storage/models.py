"""Serializable results returned by the run repository."""

from dataclasses import dataclass
from typing import Literal

ArtifactState = Literal[
    "available", "missing", "invalid", "unavailable", "unsafe", "too_large"
]


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
