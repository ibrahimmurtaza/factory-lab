"""Project profiling: combines inspection and detection into a profile."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Protocol

from factory.config.manager import ConfigManager
from factory.control.projects.models import Project
from factory.control.projects.service import ProjectService
from factory.errors import ProjectNotFoundError
from factory.intelligence.detection.base import DetectionContext, DetectorRegistry
from factory.intelligence.repository.inspector import (
    InspectionContext,
    RepositoryInspector,
)
from factory.intelligence.repository.models import (
    Detection,
    GitMetadata,
    ProjectProfile,
    RepositoryStructure,
)

__all__ = ["ProjectProfiler"]


class ProjectRepository(Protocol):
    """Storage port for registered projects (subset used by the profiler)."""

    def list_projects(self) -> List[Project]: ...


class ProjectProfiler:
    """Builds a :class:`ProjectProfile` for a registered project.

    The profiler depends on injectable ports so inspection and detection
    remain independent of CLI presentation and persistence.
    """

    def __init__(
        self,
        config_manager: ConfigManager,
        inspector: RepositoryInspector,
        registry: DetectorRegistry,
    ) -> None:
        self._config_manager = config_manager
        self._inspector = inspector
        self._registry = registry

    def profile(self, project_id: str) -> ProjectProfile:
        """Profile the registered project with ``project_id``.

        Raises:
            ProjectNotFoundError: If the project id is unknown.
            FileNotFoundError: If the repository directory no longer exists.
            NotADirectoryError: If the project path is not a directory.
        """
        service = ProjectService(self._config_manager)
        project = service.get_project(project_id)

        inspection_context = self._inspector.inspect(project.path)
        git_metadata = self._inspector.git_metadata(project.path)

        detection_context = DetectionContext(
            root=inspection_context.root,
            files=inspection_context.all_files,
            manifest_contents=inspection_context.manifest_contents,
        )
        detections = self._registry.detect_all(detection_context)

        languages, frameworks, infrastructure = self._categorize(detections)

        return ProjectProfile(
            project_id=project.id,
            project_name=project.name,
            repository_root=inspection_context.structure.root,
            inspected_at=datetime.now(timezone.utc).isoformat(),
            languages=languages,
            frameworks=frameworks,
            infrastructure=infrastructure,
            structure=inspection_context.structure,
            git_metadata=git_metadata,
            detections=detections,
        )

    @staticmethod
    def _categorize(
        detections: List[Detection],
    ) -> tuple[List[Detection], List[Detection], List[Detection]]:
        languages = [d for d in detections if d.category == "language"]
        frameworks = [d for d in detections if d.category == "framework"]
        infrastructure = [d for d in detections if d.category == "infrastructure"]
        return languages, frameworks, infrastructure
