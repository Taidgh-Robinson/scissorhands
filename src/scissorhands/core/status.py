"""Per-criterion claims reported by the agent."""

from dataclasses import dataclass

STATUS_FILE = "status.json"


@dataclass(frozen=True, slots=True)
class CriterionStatus:
    """The agent's assessment of one checklist item; `met` is None when unreported."""

    id: str
    text: str
    met: bool | None
    evidence: str = ""
