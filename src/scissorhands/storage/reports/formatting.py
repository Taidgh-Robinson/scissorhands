"""Shared Markdown table formatting for persisted reports."""

from scissorhands.core.iteration import IterationRecord


def table_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def criterion_state(record: IterationRecord | None, item_id: str) -> str:
    if record is None:
        return "unknown"
    if not record.status_updated:
        return "stale"
    if record.statuses is None:
        return "unreadable"
    item = next((item for item in record.statuses if item.id == item_id), None)
    if item is None or item.met is None:
        return "unreported"
    return "met" if item.met else "unmet"


def verification_state(record: IterationRecord | None, command: str) -> str:
    if record is None:
        return "unknown"
    if record.verification is None:
        return "not run" if record.verification_required else "not configured"
    item = next(
        (item for item in record.verification.results if item.command == command), None
    )
    if item is None:
        return "not run"
    return "passed" if item.passed else f"failed (exit {item.return_code})"
