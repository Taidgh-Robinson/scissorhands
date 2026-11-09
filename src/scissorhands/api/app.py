"""FastAPI reporting routes over registered project folders."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status

from scissorhands.api.registry import (
    DuplicateProjectError,
    Project,
    ProjectRegistry,
    default_registry_path,
)
from scissorhands.api.schemas import (
    ArtifactResponse,
    ListedRunResponse,
    LoopDetailResponse,
    ProjectInput,
    ProjectResponse,
    RunDetailResponse,
    RunSummaryResponse,
)
from scissorhands.application import RunRepository
from scissorhands.storage.artifacts import DEFAULT_TEXT_BYTES, MAX_TEXT_BYTES


def _registry(request: Request) -> ProjectRegistry:
    return request.app.state.registry


Registry = Annotated[ProjectRegistry, Depends(_registry)]


def create_app(registry_path: Path | None = None) -> FastAPI:
    """Build an isolated app; tests and servers may choose their own registry file."""
    app = FastAPI(title="Scissorhands Reporting API")
    app.state.registry = ProjectRegistry(registry_path or default_registry_path())

    def project_or_404(project_id: str, projects: ProjectRegistry) -> Project:
        project = projects.get(project_id)
        if project is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
        return project

    def repository(project_id: str, projects: ProjectRegistry) -> RunRepository:
        project = project_or_404(project_id, projects)
        if not project.available:
            raise HTTPException(status.HTTP_409_CONFLICT, "Project folder is unavailable")
        return RunRepository(project.root)

    def query(action):
        try:
            return action()
        except FileNotFoundError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except ValueError as error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error

    @app.get("/api/projects", response_model=list[ProjectResponse])
    def list_projects(projects: Registry):
        return [_project_payload(project) for project in projects.list()]

    @app.post(
        "/api/projects",
        response_model=ProjectResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def add_project(body: ProjectInput, projects: Registry):
        if not Path(body.path).is_absolute():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Project path must be absolute")
        try:
            project = projects.add(Path(body.path), name=body.name)
        except DuplicateProjectError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
        return _project_payload(project)

    @app.get("/api/projects/{project_id}", response_model=ProjectResponse)
    def get_project(project_id: str, projects: Registry):
        return _project_payload(project_or_404(project_id, projects))

    @app.delete("/api/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
    def remove_project(project_id: str, projects: Registry):
        if not projects.remove(project_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")

    @app.get("/api/runs", response_model=list[ListedRunResponse])
    def list_all_runs(projects: Registry):
        runs = []
        for project in projects.list():
            if not project.available:
                continue
            summaries = query(lambda root=project.root: RunRepository(root).list_runs())
            runs.extend({"project_id": project.id, **asdict(run)} for run in summaries)
        return runs

    @app.get("/api/projects/{project_id}/work-items", response_model=list[str])
    def list_work_items(project_id: str, projects: Registry):
        return query(lambda: repository(project_id, projects).list_work_items())

    @app.get(
        "/api/projects/{project_id}/runs", response_model=list[RunSummaryResponse]
    )
    def list_project_runs(
        project_id: str, projects: Registry, work_item_id: str | None = None
    ):
        runs = query(
            lambda: repository(project_id, projects).list_runs(work_item_id)
        )
        return [asdict(run) for run in runs]

    run_prefix = (
        "/api/projects/{project_id}/work-items/{work_item_id}/runs/{run_id}"
    )

    @app.get(run_prefix, response_model=RunDetailResponse)
    def get_run(project_id: str, work_item_id: str, run_id: str, projects: Registry):
        return asdict(
            query(lambda: repository(project_id, projects).read_run(work_item_id, run_id))
        )

    @app.get(run_prefix + "/loops/{number}", response_model=LoopDetailResponse)
    def get_loop(
        project_id: str, work_item_id: str, run_id: str, number: int, projects: Registry
    ):
        return asdict(
            query(
                lambda: repository(project_id, projects).read_loop(
                    work_item_id, run_id, number
                )
            )
        )

    def artifact(
        project_id: str,
        work_item_id: str,
        run_id: str,
        kind: str,
        projects: ProjectRegistry,
        *,
        loop: int | None = None,
        verification: int | None = None,
        offset: int = 0,
        limit: int = DEFAULT_TEXT_BYTES,
        tail: bool = False,
    ):
        return asdict(
            query(
                lambda: repository(project_id, projects).read_artifact(
                    work_item_id,
                    run_id,
                    kind,
                    loop=loop,
                    verification=verification,
                    offset=offset,
                    limit=limit,
                    tail=tail,
                )
            )
        )

    @app.get(run_prefix + "/artifacts/{kind}", response_model=ArtifactResponse)
    def get_run_artifact(
        project_id: str,
        work_item_id: str,
        run_id: str,
        kind: str,
        projects: Registry,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=MAX_TEXT_BYTES)] = DEFAULT_TEXT_BYTES,
        tail: bool = False,
    ):
        return artifact(
            project_id, work_item_id, run_id, kind, projects,
            offset=offset, limit=limit, tail=tail,
        )

    @app.get(
        run_prefix + "/loops/{number}/artifacts/{kind}",
        response_model=ArtifactResponse,
    )
    def get_loop_artifact(
        project_id: str,
        work_item_id: str,
        run_id: str,
        number: int,
        kind: str,
        projects: Registry,
        verification: Annotated[int | None, Query(ge=1)] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=MAX_TEXT_BYTES)] = DEFAULT_TEXT_BYTES,
        tail: bool = False,
    ):
        return artifact(
            project_id, work_item_id, run_id, kind, projects,
            loop=number, verification=verification, offset=offset, limit=limit, tail=tail,
        )

    return app


def _project_payload(project: Project) -> dict[str, str | bool]:
    return {
        "id": project.id,
        "name": project.name,
        "path": str(project.root),
        "created_at": project.created_at,
        "available": project.available,
    }
