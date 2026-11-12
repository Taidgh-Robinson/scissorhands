"""FastAPI reporting routes over registered project folders."""

from __future__ import annotations

import os
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
    ErrorResponse,
    LoopArtifactKind,
    LoopDetailResponse,
    ProjectInput,
    ProjectResponse,
    RunArtifactKind,
    RunDetailResponse,
    RunListResponse,
    RunSummaryResponse,
    WorkItemCreateResponse,
    WorkItemInput,
)
from scissorhands.application import RunRepository
from scissorhands.storage.artifacts import DEFAULT_TEXT_BYTES, MAX_TEXT_BYTES
from scissorhands.storage.work_items import build_work_item, dump_work_item


def _registry(request: Request) -> ProjectRegistry:
    return request.app.state.registry


Registry = Annotated[ProjectRegistry, Depends(_registry)]

READ_ERRORS = {
    400: {
        "model": ErrorResponse,
        "description": "Invalid artifact options or storage path",
    },
    404: {
        "model": ErrorResponse,
        "description": "Project, work item, run, or loop not found",
    },
    409: {
        "model": ErrorResponse,
        "description": "Project folder unavailable or unreadable",
    },
}


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
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Project folder is unavailable"
            )
        return RunRepository(project.root)

    def query(action):
        try:
            return action()
        except FileNotFoundError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except OSError as error:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Project storage is unreadable"
            ) from error
        except ValueError as error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error

    @app.get("/api/projects", response_model=list[ProjectResponse])
    def list_projects(projects: Registry):
        return [_project_payload(project) for project in projects.list()]

    @app.post(
        "/api/projects",
        response_model=ProjectResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            400: {
                "model": ErrorResponse,
                "description": "Invalid or inaccessible project path or name",
            },
            409: {"model": ErrorResponse, "description": "Project already registered"},
        },
    )
    def add_project(body: ProjectInput, projects: Registry):
        if not Path(body.path).is_absolute():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Project path must be absolute"
            )
        try:
            project = projects.add(Path(body.path), name=body.name)
        except DuplicateProjectError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
        except (OSError, RuntimeError) as error:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Project path is inaccessible"
            ) from error
        return _project_payload(project)

    @app.get(
        "/api/projects/{project_id}",
        response_model=ProjectResponse,
        responses={404: READ_ERRORS[404]},
    )
    def get_project(project_id: str, projects: Registry):
        return _project_payload(project_or_404(project_id, projects))

    @app.delete(
        "/api/projects/{project_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        responses={404: READ_ERRORS[404]},
    )
    def remove_project(project_id: str, projects: Registry):
        if not projects.remove(project_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")

    @app.get(
        "/api/runs",
        response_model=RunListResponse,
        description="Return readable projects' runs and per-project read errors. A failed project contributes no runs.",
    )
    def list_all_runs(projects: Registry):
        runs = []
        errors = []
        for project in projects.list():
            try:
                summaries = query(
                    lambda project=project: repository(project.id, projects).list_runs()
                )
            except HTTPException as error:
                errors.append(
                    {
                        "project_id": project.id,
                        "status_code": error.status_code,
                        "detail": error.detail,
                    }
                )
                continue
            runs.extend({"project_id": project.id, **asdict(run)} for run in summaries)
        return {"runs": runs, "errors": errors}

    @app.get(
        "/api/projects/{project_id}/work-items",
        response_model=list[str],
        responses=READ_ERRORS,
    )
    def list_work_items(project_id: str, projects: Registry):
        return query(lambda: repository(project_id, projects).list_work_items())

    @app.post(
        "/api/projects/{project_id}/work-items",
        response_model=WorkItemCreateResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            400: {
                "model": ErrorResponse,
                "description": "Invalid work-item fields or destination path",
            },
            404: READ_ERRORS[404],
            409: {
                "model": ErrorResponse,
                "description": "Project unavailable, or the file exists and overwrite was not set",
            },
        },
    )
    def add_work_item(project_id: str, body: WorkItemInput, projects: Registry):
        project = project_or_404(project_id, projects)
        if not project.available:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Project folder is unavailable"
            )

        fields = body.model_dump(exclude={"path", "overwrite"})
        try:
            work_item = build_work_item(fields, source="request body")
        except ValueError as error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error

        candidate = Path(body.path)
        if candidate.is_absolute():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "path must be relative to the project"
            )
        target = (project.root / candidate).resolve()
        if not target.is_relative_to(project.root):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "path must stay within the project"
            )
        if target.is_symlink():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "path must not be a symlink"
            )
        if target.is_dir():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "path is a directory")
        if target.exists() and not body.overwrite:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "File already exists; pass overwrite=true to replace it",
            )

        text = dump_work_item(work_item)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if body.overwrite:
                temporary = target.with_name(f"{target.name}.tmp")
                temporary.write_text(text, encoding="utf-8")
                temporary.replace(target)
            else:
                # O_EXCL makes "already exists" an atomic check, closing the race
                # between the precheck above and this write.
                fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                try:
                    os.write(fd, text.encode("utf-8"))
                finally:
                    os.close(fd)
        except FileExistsError:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "File already exists; pass overwrite=true to replace it",
            ) from None
        except OSError as error:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Unable to write work item file"
            ) from error

        return {
            "path": str(target.relative_to(project.root)),
            "toml": text,
            "work_item": asdict(work_item),
        }

    @app.get(
        "/api/projects/{project_id}/runs",
        response_model=list[RunSummaryResponse],
        responses=READ_ERRORS,
    )
    def list_project_runs(
        project_id: str, projects: Registry, work_item_id: str | None = None
    ):
        runs = query(lambda: repository(project_id, projects).list_runs(work_item_id))
        return [asdict(run) for run in runs]

    run_prefix = "/api/projects/{project_id}/work-items/{work_item_id}/runs/{run_id}"

    @app.get(run_prefix, response_model=RunDetailResponse, responses=READ_ERRORS)
    def get_run(project_id: str, work_item_id: str, run_id: str, projects: Registry):
        return asdict(
            query(
                lambda: repository(project_id, projects).read_run(work_item_id, run_id)
            )
        )

    @app.get(
        run_prefix + "/loops/{number}",
        response_model=LoopDetailResponse,
        responses=READ_ERRORS,
    )
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

    @app.get(
        run_prefix + "/artifacts/{kind}",
        response_model=ArtifactResponse,
        responses=READ_ERRORS,
    )
    def get_run_artifact(
        project_id: str,
        work_item_id: str,
        run_id: str,
        kind: RunArtifactKind,
        projects: Registry,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=MAX_TEXT_BYTES)] = DEFAULT_TEXT_BYTES,
        tail: bool = False,
    ):
        return artifact(
            project_id,
            work_item_id,
            run_id,
            kind,
            projects,
            offset=offset,
            limit=limit,
            tail=tail,
        )

    @app.get(
        run_prefix + "/loops/{number}/artifacts/{kind}",
        response_model=ArtifactResponse,
        responses=READ_ERRORS,
    )
    def get_loop_artifact(
        project_id: str,
        work_item_id: str,
        run_id: str,
        number: int,
        kind: LoopArtifactKind,
        projects: Registry,
        verification: Annotated[int | None, Query(ge=1)] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=MAX_TEXT_BYTES)] = DEFAULT_TEXT_BYTES,
        tail: bool = False,
    ):
        return artifact(
            project_id,
            work_item_id,
            run_id,
            kind,
            projects,
            loop=number,
            verification=verification,
            offset=offset,
            limit=limit,
            tail=tail,
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
