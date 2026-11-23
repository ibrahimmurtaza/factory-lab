"""Project registration domain model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Project:
    """A registered software project.

    Attributes:
        id: Stable, unique identifier for the project.
        name: Human-readable name derived from the repository directory.
        path: Absolute canonical path to the project repository.
        created_at: ISO-8601 timestamp when the project was registered.
    """

    id: str
    name: str
    path: str
    created_at: str
