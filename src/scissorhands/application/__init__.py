"""Shared entry points for CLI and future API interfaces.

Keep request parsing, HTTP schemas, and terminal presentation in their adapters.
"""

from scissorhands.application.models import RunPreview, RunRequest
from scissorhands.application.runs import RunService
from scissorhands.core.loop.observer import RunObserver
from scissorhands.storage.repository import RunRepository

__all__ = ["RunObserver", "RunPreview", "RunRepository", "RunRequest", "RunService"]
