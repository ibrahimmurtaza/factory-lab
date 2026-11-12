"""Tests for project registration service."""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.control.projects.service import ProjectService
from factory.config.manager import ConfigManager, JsonConfigStorage
from factory.errors import DuplicateProjectError, InvalidProjectPathError


def _service(tmp_path: Path) -> ProjectService:
    storage = JsonConfigStorage(tmp_path / "config.json")
    manager = ConfigManager(storage)
    return ProjectService(manager)


def test_successful_project_registration(tmp_path):
    service = _service(tmp_path)
    project = service.add_project(str(tmp_path))
    assert project.path == str(tmp_path.resolve())
    assert project.name == tmp_path.name
    assert project.id
    assert project.created_at


def test_nonexistent_path_raises(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(InvalidProjectPathError):
        service.add_project(str(tmp_path / "does-not-exist"))


def test_file_instead_of_directory_raises(tmp_path):
    service = _service(tmp_path)
    file_path = tmp_path / "afile.txt"
    file_path.write_text("x")
    with pytest.raises(InvalidProjectPathError):
        service.add_project(str(file_path))


def test_duplicate_path_registration_raises(tmp_path):
    service = _service(tmp_path)
    service.add_project(str(tmp_path))
    with pytest.raises(DuplicateProjectError):
        service.add_project(str(tmp_path))


def test_multiple_project_registration(tmp_path):
    service = _service(tmp_path)
    p1 = service.add_project(str(tmp_path))
    sub = tmp_path / "sub"
    sub.mkdir()
    p2 = service.add_project(str(sub))
    projects = service.list_projects()
    assert len(projects) == 2
    assert {p.id for p in projects} == {p1.id, p2.id}


def test_list_empty_registry(tmp_path):
    service = _service(tmp_path)
    assert service.list_projects() == []
