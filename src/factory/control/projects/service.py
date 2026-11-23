"""Project registration service."""

from __future__ import annotations

from pathlib import Path
from typing import List, Protocol

from factory.config.manager import ConfigManager
from factory.control.projects.models import Project
from factory.errors import (
    DuplicateProjectError,
    InvalidProjectPathError,
    ProjectNotFoundError,
)


class ProjectRepository(Protocol):
    """Storage port for registered projects."""

    def list_projects(self) -> List[Project]: ...
    def add_project(self, project: Project) -> None: ...


class ProjectService:
    """Business logic for registering and listing projects.

    The service depends on a :class:`ProjectRepository` port so persistence
    can be swapped without changing orchestration logic.
    """

    def __init__(self, repository: ProjectRepository) -> None:
        self._repository = repository

    def list_projects(self) -> List[Project]:
        """Return all registered projects."""
        return self._repository.list_projects()

    def add_project(self, path: str) -> Project:
        """Register a project at ``path``.

        Args:
            path: Local filesystem path to a project directory.

        Returns:
            The newly registered :class:`Project`.

        Raises:
            InvalidProjectPathError: If ``path`` does not exist or is not a
                directory.
            DuplicateProjectError: If a project with the same canonical path is
                already registered.
        """
        resolved = Path(path).expanduser().resolve(strict=False)

        if not resolved.exists():
            raise InvalidProjectPathError(
                f"Project path does not exist: {path}", detail=str(resolved)
            )
        if not resolved.is_dir():
            raise InvalidProjectPathError(
                f"Project path is not a directory: {path}", detail=str(resolved)
            )

        canonical = str(resolved)
        for existing in self._repository.list_projects():
            if existing.path == canonical:
                raise DuplicateProjectError(
                    f"Project already registered: {path}", detail=canonical
                )

        project = Project(
            id=self._generate_id(),
            name=resolved.name or resolved.stem,
            path=canonical,
            created_at=self._now(),
        )
        self._repository.add_project(project)
        return project

    def get_project(self, project_id: str) -> Project:
        """Return the registered project with ``project_id``.

        Args:
            project_id: Stable identifier of a registered project.

        Returns:
            The matching :class:`Project`.

        Raises:
            ProjectNotFoundError: If no project has the given identifier.
        """
        for project in self._repository.list_projects():
            if project.id == project_id:
                return project
        raise ProjectNotFoundError(
            f"Unknown project id: {project_id}", detail=project_id
        )

    @staticmethod
    def _generate_id() -> str:
        import uuid

        return str(uuid.uuid4())

    @staticmethod
    def _now() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()
