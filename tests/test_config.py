"""Tests for configuration management."""

from __future__ import annotations

import json

import pytest

from factory.config.manager import (
    ConfigData,
    ConfigManager,
    JsonConfigStorage,
    default_config_path,
)
from factory.control.projects.models import Project
from factory.errors import ConfigError


def _storage(tmp_path: Path) -> JsonConfigStorage:
    return JsonConfigStorage(tmp_path / "config.json")


def test_missing_config_returns_empty_registry(tmp_path):
    storage = _storage(tmp_path)
    manager = ConfigManager(storage)
    data = manager.load()
    assert data.projects == []
    assert data.version == 1


def test_initialize_creates_config_file(tmp_path):
    target = tmp_path / "config.json"
    manager = ConfigManager(JsonConfigStorage(target))
    data = manager.initialize(target)
    assert data.projects == []
    assert target.exists()
    assert json.loads(target.read_text())["version"] == 1


def test_initialize_repeated_does_not_overwrite(tmp_path):
    target = tmp_path / "config.json"
    storage = JsonConfigStorage(target)
    manager = ConfigManager(storage)
    manager.initialize(target)

    project = Project(id="fixed", name="proj", path=str(tmp_path), created_at="t")
    manager.register_project(project)

    # Re-initializing must not wipe existing data.
    manager.initialize(target)
    data = manager.load()
    assert len(data.projects) == 1
    assert data.projects[0].id == "fixed"


def test_malformed_json_raises_config_error(tmp_path):
    target = tmp_path / "config.json"
    target.write_text("{not valid json", encoding="utf-8")
    manager = ConfigManager(JsonConfigStorage(target))
    with pytest.raises(ConfigError):
        manager.load()


def test_roundtrip_persistence(tmp_path):
    target = tmp_path / "config.json"
    project = Project(
        id="abc-123", name="example", path=str(tmp_path), created_at="2024-01-01T00:00:00+00:00"
    )

    first = ConfigManager(JsonConfigStorage(target))
    first.register_project(project)

    second = ConfigManager(JsonConfigStorage(target))
    loaded = second.list_projects()
    assert len(loaded) == 1
    assert loaded[0] == project


def test_duplicate_registration_prevented(tmp_path):
    target = tmp_path / "config.json"
    manager = ConfigManager(JsonConfigStorage(target))
    project = Project(id="x", name="proj", path=str(tmp_path), created_at="t")
    manager.register_project(project)
    with pytest.raises(ValueError):
        manager.register_project(project)


def test_default_config_path_is_home_based():
    path = default_config_path()
    assert path.parent.name == ".factory-lab"
    assert path.name == "config.json"
    assert path.is_absolute()


def test_config_data_defaults():
    data = ConfigData()
    assert data.version == 1
    assert data.projects == []
