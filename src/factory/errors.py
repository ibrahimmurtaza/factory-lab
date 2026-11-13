"""Domain errors for Factory Lab."""

from __future__ import annotations

from typing import Optional


class FactoryLabError(Exception):
    """Base exception for all Factory Lab errors."""

    def __init__(self, message: str, detail: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def __str__(self) -> str:  # pragma: no cover - trivial
        if self.detail:
            return f"{self.message} ({self.detail})"
        return self.message


class ConfigError(FactoryLabError):
    """Raised when configuration cannot be read or written."""


class ProjectError(FactoryLabError):
    """Base exception for project-related errors."""


class DuplicateProjectError(ProjectError):
    """Raised when a project is already registered."""


class ProjectNotFoundError(ProjectError):
    """Raised when a project identifier is unknown."""


class InvalidProjectPathError(ProjectError):
    """Raised when a project path is missing or not a directory."""


class TaskError(FactoryLabError):
    """Base exception for all task-related errors."""


class TaskNotFoundError(TaskError):
    """Raised when a task identifier is unknown."""


class TaskValidationError(TaskError):
    """Raised when task input fails validation."""


class InvalidTaskTransitionError(TaskError):
    """Raised when a requested lifecycle transition is not permitted."""


class ProjectInspectionError(TaskError):
    """Raised when project profiling fails during planning."""


class PlanningError(TaskError):
    """Raised when plan generation fails."""


class PlanValidationError(TaskError):
    """Raised when an implementation plan fails structural validation."""


class ActorResolutionError(TaskError):
    """Raised when the actor identity cannot be resolved."""


class TaskStorageError(TaskError):
    """Raised when task persistence operations fail."""
