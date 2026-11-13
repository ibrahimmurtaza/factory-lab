"""Tests for TaskService create, list, get (M4-04).

Task dependencies (TaskStorage, ProjectService, ProjectProfiler,
TaskPlanner, ActorResolver) are mocked so these tests exercise only the
service layer. No network, no external processes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from factory.control.task import TaskService
from factory.control.task_models import (
    LifecycleEvent,
    TaskRecord,
    TaskStatus,
)
from factory.errors import (
    ProjectNotFoundError,
    TaskNotFoundError,
    TaskValidationError,
)


def _make_service():
    storage = MagicMock()
    project_service = MagicMock()
    profiler = MagicMock()
    planner = MagicMock()
    actor_resolver = MagicMock()
    service = TaskService(
        storage=storage,
        project_service=project_service,
        profiler=profiler,
        planner=planner,
        actor_resolver=actor_resolver,
    )
    return service, storage, project_service, profiler, planner, actor_resolver


def _record(task_id="task_abc123", project_id="proj-1"):
    return TaskRecord(
        task_id=task_id,
        project_id=project_id,
        description="implement the feature",
        status=TaskStatus.CREATED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        current_revision=None,
    )


def test_create_task_returns_created_record():
    service, storage, project_service, *_ = _make_service()
    project_service.get_project.return_value = MagicMock(id="proj-1")

    record = service.create_task("proj-1", "implement the feature")

    assert record.status == TaskStatus.CREATED
    assert record.current_revision is None
    assert record.task_id.startswith("task_")
    assert record.project_id == "proj-1"
    assert record.description == "implement the feature"
    assert record.created_at is not None
    assert record.updated_at is not None


def test_create_task_persists_via_storage():
    service, storage, project_service, *_ = _make_service()
    project_service.get_project.return_value = MagicMock(id="proj-1")

    record = service.create_task("proj-1", "implement the feature")

    storage.save.assert_called_once()
    saved_id, saved_record = storage.save.call_args[0]
    assert saved_id == record.task_id
    assert saved_record is record


def test_create_task_records_lifecycle_event():
    service, storage, project_service, *_ = _make_service()
    project_service.get_project.return_value = MagicMock(id="proj-1")

    record = service.create_task("proj-1", "implement the feature")

    assert len(record.lifecycle_history) == 1
    event = record.lifecycle_history[0]
    assert isinstance(event, LifecycleEvent)
    assert event.from_status is None
    assert event.to_status == TaskStatus.CREATED
    assert event.timestamp is not None
    assert event.actor is None


def test_create_task_unknown_project_raises_project_not_found():
    service, storage, project_service, *_ = _make_service()
    project_service.get_project.side_effect = ProjectNotFoundError(
        "Unknown project id: nope", detail="nope"
    )

    with pytest.raises(ProjectNotFoundError):
        service.create_task("nope", "implement the feature")

    storage.save.assert_not_called()


def test_create_task_empty_project_id_raises():
    service, *_ = _make_service()

    with pytest.raises(TaskValidationError):
        service.create_task("", "implement the feature")


def test_create_task_whitespace_project_id_raises():
    service, *_ = _make_service()

    with pytest.raises(TaskValidationError):
        service.create_task("   ", "implement the feature")


def test_create_task_empty_description_raises():
    service, *_ = _make_service()

    with pytest.raises(TaskValidationError):
        service.create_task("proj-1", "")


def test_create_task_whitespace_description_raises():
    service, *_ = _make_service()

    with pytest.raises(TaskValidationError):
        service.create_task("proj-1", "   ")


def test_create_task_does_not_call_project_profiler():
    service, storage, project_service, profiler, *_ = _make_service()
    project_service.get_project.return_value = MagicMock(id="proj-1")

    service.create_task("proj-1", "implement the feature")

    profiler.profile.assert_not_called()


def test_list_tasks_returns_storage_records():
    service, storage, *_ = _make_service()
    expected = [_record("task_aaa"), _record("task_bbb")]
    storage.list_all.return_value = expected

    result = service.list_tasks()

    assert result == expected
    storage.list_all.assert_called_once()


def test_get_task_returns_record():
    service, storage, *_ = _make_service()
    record = _record()
    storage.load.return_value = record

    result = service.get_task("task_abc123")

    assert result is record
    storage.load.assert_called_once_with("task_abc123")


def test_get_task_unknown_id_raises_task_not_found():
    service, storage, *_ = _make_service()
    storage.load.return_value = None

    with pytest.raises(TaskNotFoundError):
        service.get_task("task_missing")


def test_get_task_path_traversal_rejected():
    service, *_ = _make_service()

    with pytest.raises(TaskValidationError):
        service.get_task("../../etc/passwd")


def test_get_task_empty_id_raises():
    service, *_ = _make_service()

    with pytest.raises(TaskValidationError):
        service.get_task("")


def test_get_task_whitespace_id_raises():
    service, *_ = _make_service()

    with pytest.raises(TaskValidationError):
        service.get_task("   ")


def test_get_task_invalid_format_rejected():
    service, *_ = _make_service()

    with pytest.raises(TaskValidationError):
        service.get_task("not-a-task-id")
