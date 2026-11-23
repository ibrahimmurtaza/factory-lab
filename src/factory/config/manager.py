"""Configuration management and JSON persistence.

The configuration storage is intentionally small and replaceable. A
:class:`ConfigStorage` port defines the contract; :class:`JsonConfigStorage`
is the current file-backed implementation.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Protocol

from factory.errors import ConfigError

__all__ = [
    "ConfigData",
    "JsonConfigStorage",
    "ConfigManager",
    "ConfigStorage",
    "default_config_path",
]


CONFIG_DIR_NAME = ".factory-lab"
CONFIG_FILE_NAME = "config.json"
CONFIG_VERSION = 1


def default_config_path() -> Path:
    """Return the platform-appropriate configuration file path.

    On Windows this lives under the user's home directory; on other platforms
    it lives under the user's home directory as well, keeping behavior
    predictable across machines.
    """
    return Path.home() / CONFIG_DIR_NAME / CONFIG_FILE_NAME


@dataclass
class ConfigData:
    """In-memory representation of the configuration file."""

    version: int = CONFIG_VERSION
    projects: List[Project] = field(default_factory=list)


class ConfigStorage(Protocol):
    """Port for reading and writing configuration data."""

    def load(self) -> ConfigData: ...
    def save(self, data: ConfigData) -> None: ...


class JsonConfigStorage:
    """JSON file-backed configuration storage.

    Writes are performed atomically by writing to a temporary file in the same
    directory and then replacing the target, which avoids leaving a partially
    written config file on disk.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def _ensure_parent(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> ConfigData:
        """Load configuration from disk.

        A missing configuration file yields an empty registry. Malformed JSON
        raises :class:`ConfigError` with an actionable message.
        """
        if not self._path.exists():
            return ConfigData()

        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - defensive
            raise ConfigError(
                f"Unable to read configuration file: {self._path}",
                detail=str(exc),
            ) from exc

        if not raw.strip():
            return ConfigData()

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"Malformed configuration file: {self._path}",
                detail="Ensure the file contains valid JSON.",
            ) from exc

        if not isinstance(payload, dict):
            raise ConfigError(
                f"Malformed configuration file: {self._path}",
                detail="Expected a JSON object at the top level.",
            )

        version = payload.get("version", CONFIG_VERSION)
        from factory.control.projects.models import Project

        projects: List[Project] = []
        for entry in payload.get("projects", []):
            try:
                projects.append(
                    Project(
                        id=entry["id"],
                        name=entry["name"],
                        path=entry["path"],
                        created_at=entry.get("created_at", ""),
                    )
                )
            except (KeyError, TypeError) as exc:
                raise ConfigError(
                    f"Malformed project entry in configuration file: {self._path}",
                    detail=str(exc),
                ) from exc

        return ConfigData(version=version, projects=projects)

    def save(self, data: ConfigData) -> None:
        """Persist configuration to disk atomically."""
        self._ensure_parent()

        payload = {
            "version": data.version,
            "projects": [
                {
                    "id": p.id,
                    "name": p.name,
                    "path": p.path,
                    "created_at": p.created_at,
                }
                for p in data.projects
            ],
        }

        serialized = json.dumps(payload, indent=2) + "\n"

        fd, tmp_name = tempfile.mkstemp(
            prefix=f"{CONFIG_FILE_NAME}.", suffix=".tmp", dir=str(self._path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(serialized)
            os.replace(tmp_name, self._path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:  # pragma: no cover - defensive
                pass
            raise


class ConfigManager:
    """High-level configuration service.

    Coordinates loading, saving, and project registry mutations through a
    :class:`ConfigStorage` port.
    """

    def __init__(self, storage: ConfigStorage) -> None:
        self._storage = storage

    def load(self) -> ConfigData:
        """Load the current configuration."""
        return self._storage.load()

    def save(self, data: ConfigData) -> None:
        """Persist the given configuration."""
        self._storage.save(data)

    def initialize(self, path: Optional[Path] = None) -> ConfigData:
        """Initialize the configuration file if it does not already exist.

        Repeated initialization is safe: an existing file is left untouched.
        """
        target = Path(path) if path is not None else default_config_path()
        if target.exists():
            return self.load()

        target.parent.mkdir(parents=True, exist_ok=True)
        self._storage.save(ConfigData())
        return ConfigData()

    def add_project(self, project: Project) -> None:
        """Append a project to the registry and persist.

        Duplicate detection is the responsibility of the caller (for example,
        :class:`ProjectService`).
        """
        data = self.load()
        data.projects.append(project)
        self.save(data)

    def register_project(self, project: Project) -> ConfigData:
        """Register a project, preventing duplicates by canonical path."""
        data = self.load()
        for existing in data.projects:
            if existing.path == project.path:
                raise ValueError(f"Project already registered: {project.path}")
        self.add_project(project)
        return data

    def list_projects(self) -> List[Project]:
        """List all registered projects."""
        return self.load().projects
