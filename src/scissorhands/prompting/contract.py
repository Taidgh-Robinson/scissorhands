"""The iteration contract template appended to every prompt."""

from __future__ import annotations

from functools import cache
from importlib.resources import files
from pathlib import Path
from string import Template

PLACEHOLDERS = frozenset(
    {
        "iteration",
        "max_iterations",
        "marker",
        "final_iteration_note",
        "verification_feedback",
        "progress_path",
        "status_path",
    }
)


@cache
def default_contract() -> str:
    """Return the packaged default contract template."""
    return (
        files("scissorhands.prompting")
        .joinpath("contract.md")
        .read_text(encoding="utf-8")
    )


def validate_contract(text: str, source: Path | str) -> None:
    """Reject templates the loop cannot render or that cannot signal completion."""
    template = Template(text)
    if not template.is_valid():
        raise ValueError(f"{source}: invalid placeholder; write a literal $ as $$")
    unknown = set(template.get_identifiers()) - PLACEHOLDERS
    if unknown:
        raise ValueError(
            f"{source}: unknown placeholder(s): {', '.join(sorted(unknown))}"
        )
    if "marker" not in template.get_identifiers():
        raise ValueError(
            f"{source}: must include $marker so the agent can signal completion"
        )


def load_contract(path: Path) -> str:
    """Load and validate a custom contract template."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"{path}: cannot read contract: {error}") from error
    validate_contract(text, path)
    return text


def render_contract(text: str, **values: object) -> str:
    """Fill a validated contract template."""
    return Template(text).substitute(values)
