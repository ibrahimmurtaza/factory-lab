"""Typed models for repository inspection results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass(frozen=True)
class Detection:
    """A single technology detection with supporting evidence.

    Attributes:
        name: The detected technology name (e.g. "FastAPI", "Python").
        category: One of "language", "framework", or "infrastructure".
        evidence: Human-readable strings describing what was observed.
    """

    name: str
    category: str
    evidence: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class GitMetadata:
    """Read-only Git metadata observed during inspection.

    All fields are optional because a repository may not use Git, or the
    metadata may not be available without executing Git commands.
    """

    branch: Optional[str] = None
    commit: Optional[str] = None
    is_dirty: Optional[bool] = None


@dataclass(frozen=True)
class RepositoryStructure:
    """Read-only observations about a repository's layout.

    None of these fields modify the repository; they describe what exists.
    """

    root: str
    top_level_files: List[str] = field(default_factory=list)
    top_level_dirs: List[str] = field(default_factory=list)
    readme_files: List[str] = field(default_factory=list)
    doc_dirs: List[str] = field(default_factory=list)
    source_dirs: List[str] = field(default_factory=list)
    test_dirs: List[str] = field(default_factory=list)
    config_files: List[str] = field(default_factory=list)
    dependency_manifests: List[str] = field(default_factory=list)
    git_present: bool = False


@dataclass(frozen=True)
class ProjectProfile:
    """Complete structured profile of a registered project."""

    project_id: str
    project_name: str
    repository_root: str
    inspected_at: str
    languages: List[Detection]
    frameworks: List[Detection]
    infrastructure: List[Detection]
    structure: RepositoryStructure
    git_metadata: Optional[GitMetadata]
    detections: List[Detection]

    def detection_count(self) -> int:
        """Return the total number of detections."""
        return len(self.detections)
