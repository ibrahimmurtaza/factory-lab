"""Tests for JsonTaskStorage and the TaskStorage protocol."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from factory.control.task_models import (
    AffectedComponent,
    ApprovalRecord,
    ImplementationPlan,
    ImplementationStep,
    LifecycleEvent,
    PlanAssumption,
    PlanDependency,
    PlanEvidence,
    PlanRevision,
    PlanRisk,
    TestingStrategyItem,
    TaskRecord,
    TaskStatus,
)
from factory.control.task_storage import (
    JsonTaskStorage,
    SCHEMA_VERSION,
    TaskStorage,
    default_tasks_dir,
)
from factory.errors import TaskStorageError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _minimal_plan() -> ImplementationPlan:
    return ImplementationPlan(
        summary="Implement task storage",
        objectives=["persist tasks"],
        requirements=["JSON sidecar files"],
        assumptions=[],
        unresolved_questions=[],
        implementation_steps=[
            ImplementationStep(
                number=1,
                description="Write storage module",
                rationale="foundation for task persistence",
                affected_components=["task_storage.py"],
                depends_on=[],
            )
        ],
        affected_components=[
            AffectedComponent(
                name="task_storage.py",
                path="src/factory/control/task_storage.py",
                purpose="task persistence",
                evidence=["M4 spec Section 4"],
            )
        ],
        dependencies=[
            PlanDependency(name="python", reason="runtime", existing=True)
        ],
        acceptance_criteria=["save/load round-trips correctly"],
        testing_strategy=[
            TestingStrategyItem(category="unit", description="test round-trip")
        ],
        risks=[
            PlanRisk(
                description="data loss",
                impact="tasks unrecoverable",
                mitigation="atomic writes",
            )
        ],
        evidence=[
            PlanEvidence(
                source="SPEC-M4.md",
                observation="defines JSON sidecar storage",
                supports="storage design",
            )
        ],
    )


def _minimal_record(task_id: str = "task_abc123") -> TaskRecord:
    return TaskRecord(
        task_id=task_id,
        project_id="proj_1",
        description="Implement task storage",
        status=TaskStatus.CREATED,
        created_at=_now(),
        updated_at=_now(),
    )


def _record_with_revision(task_id: str = "task_abc123") -> TaskRecord:
    plan = _minimal_plan()
    approval = ApprovalRecord(
        decision="approved",
        actor="alice",
        timestamp=_now(),
    )
    revision = PlanRevision(
        revision_number=1,
        created_at=_now(),
        status="approved",
        plan=plan,
        approval=approval,
    )
    event = LifecycleEvent(
        from_status=None,
        to_status=TaskStatus.CREATED,
        timestamp=_now(),
    )
    return TaskRecord(
        task_id=task_id,
        project_id="proj_1",
        description="Implement task storage",
        status=TaskStatus.APPROVED,
        created_at=_now(),
        updated_at=_now(),
        current_revision=1,
        plan_revisions=[revision],
        lifecycle_history=[event],
    )


# ---------------------------------------------------------------------------
# default_tasks_dir
# ---------------------------------------------------------------------------

def test_default_tasks_dir_returns_home_path() -> None:
    expected = Path.home() / ".factory-lab" / "tasks"
    assert default_tasks_dir() == expected


# ---------------------------------------------------------------------------
# save / load round-trip
# ---------------------------------------------------------------------------

def test_save_and_load_round_trips_minimal_record(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    record = _minimal_record()
    storage.save("task_abc123", record)

    loaded = storage.load("task_abc123")
    assert loaded is not None
    assert loaded.task_id == "task_abc123"
    assert loaded.project_id == "proj_1"
    assert loaded.description == "Implement task storage"
    assert loaded.status == TaskStatus.CREATED
    assert loaded.current_revision is None
    assert loaded.plan_revisions == []
    assert loaded.lifecycle_history == []


def test_save_and_load_round_trips_full_record(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    record = _record_with_revision()
    storage.save("task_abc123", record)

    loaded = storage.load("task_abc123")
    assert loaded is not None
    assert loaded.task_id == "task_abc123"
    assert loaded.status == TaskStatus.APPROVED
    assert loaded.current_revision == 1
    assert len(loaded.plan_revisions) == 1
    assert loaded.plan_revisions[0].revision_number == 1
    assert loaded.plan_revisions[0].status == "approved"
    assert loaded.plan_revisions[0].approval is not None
    assert loaded.plan_revisions[0].approval.decision == "approved"
    assert loaded.plan_revisions[0].approval.actor == "alice"
    assert loaded.plan_revisions[0].plan.summary == "Implement task storage"
    assert len(loaded.lifecycle_history) == 1
    assert loaded.lifecycle_history[0].to_status == TaskStatus.CREATED


def test_persisted_record_contains_schema_version(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    storage.save("task_abc123", _minimal_record())

    path = tmp_path / "tasks" / "task_abc123.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SCHEMA_VERSION


def test_persisted_task_id_matches_filename(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    storage.save("task_xyz789", _minimal_record(task_id="task_xyz789"))

    path = tmp_path / "tasks" / "task_xyz789.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["task_id"] == "task_xyz789"


# ---------------------------------------------------------------------------
# missing file
# ---------------------------------------------------------------------------

def test_load_missing_file_returns_none(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    assert storage.load("task_does_not_exist") is None


# ---------------------------------------------------------------------------
# corrupted / malformed files
# ---------------------------------------------------------------------------

def test_load_corrupted_json_raises(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    path = tmp_path / "tasks" / "task_bad.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not valid json", encoding="utf-8")

    with pytest.raises(TaskStorageError):
        storage.load("task_bad")


def test_load_empty_file_raises(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    path = tmp_path / "tasks" / "task_empty.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")

    with pytest.raises(TaskStorageError):
        storage.load("task_empty")


def test_load_unknown_schema_version_raises(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    path = tmp_path / "tasks" / "task_v2.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 99,
        "task_id": "task_v2",
        "project_id": "proj_1",
        "description": "x",
        "status": "created",
        "created_at": _now().isoformat(),
        "updated_at": _now().isoformat(),
        "current_revision": None,
        "plan_revisions": [],
        "lifecycle_history": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(TaskStorageError) as exc_info:
        storage.load("task_v2")
    assert "Unsupported task schema version" in str(exc_info.value)


def test_load_task_id_mismatch_raises(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    path = tmp_path / "tasks" / "task_stored.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = _minimal_record(task_id="task_stored")
    storage.save("task_stored", record)
    # Corrupt the task_id field on disk so it no longer matches the filename.
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["task_id"] = "task_different"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(TaskStorageError) as exc_info:
        storage.load("task_stored")
    assert "Task ID mismatch" in str(exc_info.value)


# ---------------------------------------------------------------------------
# list_all
# ---------------------------------------------------------------------------

def test_list_all_returns_all_persisted_tasks(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    storage.save("task_001", _minimal_record(task_id="task_001"))
    storage.save("task_002", _minimal_record(task_id="task_002"))
    storage.save("task_003", _minimal_record(task_id="task_003"))

    records = storage.list_all()
    assert len(records) == 3
    assert {r.task_id for r in records} == {"task_001", "task_002", "task_003"}


def test_list_all_empty_directory(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    assert storage.list_all() == []


def test_list_all_missing_directory_returns_empty(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    # Directory never created.
    assert storage.list_all() == []


def test_list_all_raises_on_corrupted_record(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    storage.save("task_good", _minimal_record(task_id="task_good"))

    bad_path = tmp_path / "tasks" / "task_bad.json"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("{ not valid json", encoding="utf-8")

    with pytest.raises(TaskStorageError) as exc_info:
        storage.list_all()
    assert "corrupted" in str(exc_info.value).lower() or "corrupt" in str(
        exc_info.value
    ).lower()
    # The good task must not be silently dropped; the error propagates.


def test_list_all_raises_on_unknown_schema(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    path = tmp_path / "tasks" / "task_v2.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 5,
        "task_id": "task_v2",
        "project_id": "proj_1",
        "description": "x",
        "status": "created",
        "created_at": _now().isoformat(),
        "updated_at": _now().isoformat(),
        "current_revision": None,
        "plan_revisions": [],
        "lifecycle_history": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(TaskStorageError):
        storage.list_all()


# ---------------------------------------------------------------------------
# atomic write behavior
# ---------------------------------------------------------------------------

def test_save_leaves_no_temporary_files(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    storage.save("task_abc123", _minimal_record())

    tmp_files = [p for p in (tmp_path / "tasks").iterdir() if p.suffix == ".tmp"]
    assert tmp_files == []


def test_save_atomic_replace_uses_same_directory(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    storage.save("task_abc123", _minimal_record())

    assert (tmp_path / "tasks" / "task_abc123.json").exists()


def test_write_failure_cleans_up_temporary_file(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    record = _minimal_record()

    # Force os.replace to fail so the temp file must be cleaned up.
    with patch("os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            storage.save("task_abc123", record)

    tmp_files = [p for p in (tmp_path / "tasks").iterdir() if p.suffix == ".tmp"]
    assert tmp_files == []


def test_save_task_id_mismatch_raises_without_writing(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    record = _minimal_record(task_id="task_stored")

    with pytest.raises(TaskStorageError) as exc_info:
        storage.save("task_different", record)
    assert "Task ID mismatch" in str(exc_info.value)

    # Nothing should have been written.
    assert not (tmp_path / "tasks").exists()


# ---------------------------------------------------------------------------
# failed persistence does not mutate in-memory state
# ---------------------------------------------------------------------------

def test_failed_save_leaves_record_unchanged(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    record = _minimal_record(task_id="task_abc123")
    original_status = record.status
    original_description = record.description

    with patch("os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            storage.save("task_abc123", record)

    assert record.status is original_status
    assert record.description == original_description


def test_failed_load_does_not_mutate_payload(tmp_path: Path) -> None:
    storage = JsonTaskStorage(tmp_path / "tasks")
    path = tmp_path / "tasks" / "task_bad.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not valid json", encoding="utf-8")

    with pytest.raises(TaskStorageError):
        storage.load("task_bad")

    # File is untouched (not silently repaired or removed).
    assert path.read_text(encoding="utf-8") == "{ not valid json"


# ---------------------------------------------------------------------------
# TaskStorage protocol shape
# ---------------------------------------------------------------------------

def test_task_storage_protocol_has_required_methods() -> None:
    from typing import get_type_hints

    hints = get_type_hints(TaskStorage.load)
    assert "return" in hints
    assert TaskStorage is not None


def test_json_task_storage_implements_protocol() -> None:
    storage = JsonTaskStorage(Path("/tmp/factory-lab-test-tasks"))
    assert hasattr(storage, "load")
    assert hasattr(storage, "save")
    assert hasattr(storage, "list_all")
