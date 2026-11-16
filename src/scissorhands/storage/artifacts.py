"""Known artifact names and bounded, contained file reads."""

from __future__ import annotations

import json
import stat
from dataclasses import dataclass
from pathlib import Path

from scissorhands.storage.models import Artifact
from scissorhands.storage.paths import require_positive_integer

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
    "plan": "plan.json",
    "progress": "progress.md",
    "prompt": "prompt.md",
    "patch": "changes.patch",
    "verification_output": "verification-{verification}.log",
}


@dataclass(frozen=True, slots=True)
class ReadWindow:
    """A validated byte window for a text artifact."""

    offset: int = 0
    limit: int = DEFAULT_TEXT_BYTES
    tail: bool = False

    def __post_init__(self) -> None:
        if type(self.offset) is not int or self.offset < 0:
            raise ValueError("offset must be a non-negative integer")
        require_positive_integer(self.limit, "limit")
        if self.limit > MAX_TEXT_BYTES:
            raise ValueError(f"limit must be at most {MAX_TEXT_BYTES}")
        if self.tail and self.offset:
            raise ValueError("tail and offset cannot be combined")

    def start(self, size: int) -> int:
        if self.tail:
            return max(0, size - self.limit)
        return min(self.offset, size)


def artifact_filename(kind: str, loop: int | None, verification: int | None) -> str:
    """Select a known filename; never accept a caller-supplied filesystem path."""
    if verification is not None and (kind != "verification_output" or loop is None):
        raise ValueError("verification is only valid for loop verification output")
    kinds = _RUN_ARTIFACTS if loop is None else _LOOP_ARTIFACTS
    if kind not in kinds:
        raise ValueError(f"Unknown artifact kind: {kind}")
    if kind == "verification_output":
        require_positive_integer(verification, "verification")
    return kinds[kind].format(number=loop, verification=verification)


def read_artifact_file(path: Path, run_directory: Path, window: ReadWindow) -> Artifact:
    """Check containment and availability before decoding a regular file."""
    is_json = path.suffix == ".json"
    if is_json and (window.offset or window.tail):
        raise ValueError("JSON artifacts do not support offset or tail")
    try:
        resolved = path.resolve()
        if not resolved.is_relative_to(run_directory):
            return Artifact("unsafe")
        if not stat.S_ISREG(resolved.stat().st_mode):
            return Artifact("unavailable")
        with resolved.open("rb") as source:
            size = source.seek(0, 2)
            start = 0 if is_json else window.start(size)
            source.seek(start)
            content = source.read(MAX_JSON_BYTES + 1 if is_json else window.limit)
    except FileNotFoundError:
        return Artifact("missing")
    except (OSError, RuntimeError):
        return Artifact("unavailable")
    if is_json:
        return _decode_json(content, size)
    return Artifact(
        state="available",
        data=content.decode("utf-8", errors="replace"),
        offset=start,
        bytes_read=len(content),
        total_bytes=size,
        truncated=start > 0 or start + len(content) < size,
    )


def _decode_json(content: bytes, size: int) -> Artifact:
    if len(content) > MAX_JSON_BYTES:
        return Artifact("too_large", total_bytes=size)
    try:
        data = json.loads(content)
    except (ValueError, UnicodeError, RecursionError):
        return Artifact("invalid", total_bytes=size)
    if not isinstance(data, dict):
        return Artifact("invalid", total_bytes=size)
    return Artifact("available", data, bytes_read=len(content), total_bytes=size)
