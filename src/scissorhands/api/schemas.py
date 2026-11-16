"""HTTP input and output models for project and run reporting."""

from typing import Any, Literal

from pydantic import BaseModel, Field

ArtifactState = Literal[
    "available", "missing", "invalid", "unavailable", "unsafe", "too_large"
]
RunState = Literal[
    "queued", "running", "finished", "cancelled", "interrupted", "unknown"
]
RunArtifactKind = Literal[
    "manifest", "settings", "work_item", "work_item_toml", "report", "patch"
]
LoopArtifactKind = Literal[
    "receipt",
    "report",
    "agent_output",
    "final_message",
    "status",
    "plan",
    "progress",
    "prompt",
    "patch",
    "verification_output",
]


class ErrorResponse(BaseModel):
    detail: str


class ProjectReadError(ErrorResponse):
    project_id: str
    status_code: Literal[400, 404, 409]


class ProjectInput(BaseModel):
    path: str
    name: str | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    path: str
    created_at: str
    available: bool


class ArtifactResponse(BaseModel):
    state: ArtifactState
    data: dict[str, Any] | str | None
    offset: int
    bytes_read: int
    total_bytes: int | None
    truncated: bool


class RunSummaryResponse(BaseModel):
    work_item_id: str
    run_id: str
    state: RunState
    outcome: str | None
    started_at: str | None
    finished_at: str | None
    manifest_state: ArtifactState


class ListedRunResponse(RunSummaryResponse):
    project_id: str


class RunListResponse(BaseModel):
    runs: list[ListedRunResponse]
    errors: list[ProjectReadError]


class RunDetailResponse(BaseModel):
    summary: RunSummaryResponse
    manifest: ArtifactResponse
    settings: ArtifactResponse
    work_item: ArtifactResponse
    loops: list[int]


class LoopDetailResponse(BaseModel):
    work_item_id: str
    run_id: str
    number: int
    receipt: ArtifactResponse


class WorkItemInput(BaseModel):
    """Structured fields matching `scissorhands.core.work_items.WorkItem`.

    Field-level rules (non-empty strings, stripped whitespace, id format) are
    enforced once, by the same validation TOML loading uses, not duplicated here.
    """

    id: str
    title: str
    description: str
    definition_of_done: list[str] = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    verification: list[str] = Field(default_factory=list)
    relevant_paths: list[str] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    path: str = "WORK_ITEM.toml"
    overwrite: bool = False


class WorkItemCreateResponse(BaseModel):
    path: str
    toml: str
    work_item: dict[str, Any]
