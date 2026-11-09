"""HTTP input and output models for project and run reporting."""

from typing import Any

from pydantic import BaseModel


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
    state: str
    data: dict[str, Any] | str | None
    offset: int
    bytes_read: int
    total_bytes: int | None
    truncated: bool


class RunSummaryResponse(BaseModel):
    work_item_id: str
    run_id: str
    state: str
    outcome: str | None
    started_at: str | None
    finished_at: str | None
    manifest_state: str


class ListedRunResponse(RunSummaryResponse):
    project_id: str


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
