"""Task persistence layer.

Defines the :class:`TaskStorage` port and the :class:`JsonTaskStorage`
file-backed implementation. Task records are stored as one JSON sidecar file
per task under ``~/.factory-lab/tasks/<task-id>.json``.

Writes are atomic: a temporary file in the same directory is written and then
replaced with ``os.replace``, which avoids leaving a partially written task
file on disk. Serialization concerns are separated from the ``TaskRecord``
domain model; the storage layer contains no task lifecycle business logic.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Protocol

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
from factory.errors import TaskStorageError

__all__ = [
    "SCHEMA_VERSION",
    "TaskStorage",
    "JsonTaskStorage",
    "default_tasks_dir",
]

SCHEMA_VERSION = 1
FACTORY_LAB_DIR_NAME = ".factory-lab"
TASKS_SUBDIR_NAME = "tasks"


def default_tasks_dir() -> Path:
    """Return the default tasks directory.

    Returns the platform-appropriate directory for task sidecar files,
    located under the user's home directory.
    """
    return Path.home() / FACTORY_LAB_DIR_NAME / TASKS_SUBDIR_NAME


class TaskStorage(Protocol):
    """Port for reading and writing task records."""

    def load(self, task_id: str) -> Optional[TaskRecord]: ...
    def save(self, task_id: str, record: TaskRecord) -> None: ...
    def list_all(self) -> List[TaskRecord]: ...


class JsonTaskStorage:
    """JSON file-backed task storage.

    One JSON sidecar file per task is stored in a tasks directory. Each
    persisted record includes a ``schema_version`` field so future storage
    migrations can be detected. Writes are atomic via a temporary file and
    ``os.replace``.
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def _task_path(self, task_id: str) -> Path:
        return self._directory / f"{task_id}.json"

    def _ensure_directory(self) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)

    def load(self, task_id: str) -> Optional[TaskRecord]:
        """Load the task record with ``task_id`` from disk.

        Args:
            task_id: Stable identifier of the task to load.

        Returns:
            The matching :class:`TaskRecord`, or ``None`` if no file exists.

        Raises:
            TaskStorageError: If the file is malformed, has an unsupported
                schema version, or its task ID does not match the filename.
        """
        path = self._task_path(task_id)
        if not path.exists():
            return None

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - defensive
            raise TaskStorageError(
                f"Unable to read task file: {path}",
                detail=str(exc),
            ) from exc

        if not raw.strip():
            raise TaskStorageError(
                f"Malformed task file: {path}",
                detail="File is empty.",
            )

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TaskStorageError(
                f"Malformed task file: {path}",
                detail="Ensure the file contains valid JSON.",
            ) from exc

        if not isinstance(payload, dict):
            raise TaskStorageError(
                f"Malformed task file: {path}",
                detail="Expected a JSON object at the top level.",
            )

        version = payload.get("schema_version")
        if version != SCHEMA_VERSION:
            raise TaskStorageError(
                f"Unsupported task schema version: {path}",
                detail=f"Expected {SCHEMA_VERSION}, got {version!r}.",
            )

        payload_task_id = payload.get("task_id")
        if payload_task_id != task_id:
            raise TaskStorageError(
                f"Task ID mismatch in {path}",
                detail=(
                    f"Filename task id {task_id!r} does not match "
                    f"record task id {payload_task_id!r}."
                ),
            )

        try:
            return _deserialize_record(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise TaskStorageError(
                f"Malformed task file: {path}",
                detail=str(exc),
            ) from exc

    def save(self, task_id: str, record: TaskRecord) -> None:
        """Persist ``record`` to disk atomically.

        Args:
            task_id: Stable identifier under which to persist the record.
            record: The :class:`TaskRecord` to persist.

        Raises:
            TaskStorageError: If ``record.task_id`` does not match ``task_id``.
        """
        if record.task_id != task_id:
            raise TaskStorageError(
                "Task ID mismatch",
                detail=(
                    f"Requested task id {task_id!r} does not match "
                    f"record task id {record.task_id!r}."
                ),
            )

        self._ensure_directory()
        path = self._task_path(task_id)

        payload = _serialize_record(record)
        serialized = json.dumps(payload, indent=2) + "\n"

        fd, tmp_name = tempfile.mkstemp(
            prefix=f"{path.name}.", suffix=".tmp", dir=str(self._directory)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(serialized)
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:  # pragma: no cover - defensive
                pass
            raise

    def list_all(self) -> List[TaskRecord]:
        """Return all persisted task records.

        Returns:
            A list of :class:`TaskRecord` instances, sorted by filename.

        Raises:
            TaskStorageError: If any task file is corrupted or malformed;
                corrupted records are never silently omitted.
        """
        if not self._directory.exists():
            return []

        records: List[TaskRecord] = []
        errors: List[str] = []
        for path in sorted(self._directory.glob("*.json")):
            task_id = path.stem
            try:
                record = self.load(task_id)
            except TaskStorageError as exc:
                errors.append(str(exc))
                continue
            if record is not None:
                records.append(record)

        if errors:
            raise TaskStorageError(
                "One or more task records are corrupted",
                detail="; ".join(errors),
            )
        return records


# ---------------------------------------------------------------------------
# Serialization helpers (separate from TaskRecord domain fields)
# ---------------------------------------------------------------------------

def _serialize_record(record: TaskRecord) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": record.task_id,
        "project_id": record.project_id,
        "description": record.description,
        "status": record.status.value,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "current_revision": record.current_revision,
        "plan_revisions": [_serialize_revision(r) for r in record.plan_revisions],
        "lifecycle_history": [_serialize_event(e) for e in record.lifecycle_history],
    }


def _serialize_revision(revision: PlanRevision) -> dict:
    return {
        "revision_number": revision.revision_number,
        "created_at": revision.created_at.isoformat(),
        "status": revision.status,
        "plan": _serialize_plan(revision.plan),
        "approval": (
            _serialize_approval(revision.approval)
            if revision.approval is not None
            else None
        ),
    }


def _serialize_plan(plan: ImplementationPlan) -> dict:
    return {
        "summary": plan.summary,
        "objectives": list(plan.objectives),
        "requirements": list(plan.requirements),
        "assumptions": [_serialize_assumption(a) for a in plan.assumptions],
        "unresolved_questions": list(plan.unresolved_questions),
        "implementation_steps": [_serialize_step(s) for s in plan.implementation_steps],
        "affected_components": [_serialize_component(c) for c in plan.affected_components],
        "dependencies": [_serialize_dependency(d) for d in plan.dependencies],
        "acceptance_criteria": list(plan.acceptance_criteria),
        "testing_strategy": [_serialize_testing(t) for t in plan.testing_strategy],
        "risks": [_serialize_risk(r) for r in plan.risks],
        "evidence": [_serialize_evidence(e) for e in plan.evidence],
    }


def _serialize_assumption(assumption: PlanAssumption) -> dict:
    return {"description": assumption.description, "reason": assumption.reason}


def _serialize_step(step: ImplementationStep) -> dict:
    return {
        "number": step.number,
        "description": step.description,
        "rationale": step.rationale,
        "affected_components": list(step.affected_components),
        "depends_on": list(step.depends_on),
    }


def _serialize_component(component: AffectedComponent) -> dict:
    return {
        "name": component.name,
        "path": component.path,
        "purpose": component.purpose,
        "evidence": list(component.evidence),
    }


def _serialize_dependency(dependency: PlanDependency) -> dict:
    return {
        "name": dependency.name,
        "reason": dependency.reason,
        "existing": dependency.existing,
    }


def _serialize_testing(item: TestingStrategyItem) -> dict:
    return {"category": item.category, "description": item.description}


def _serialize_risk(risk: PlanRisk) -> dict:
    return {
        "description": risk.description,
        "impact": risk.impact,
        "mitigation": risk.mitigation,
    }


def _serialize_evidence(evidence: PlanEvidence) -> dict:
    return {
        "source": evidence.source,
        "observation": evidence.observation,
        "supports": evidence.supports,
    }


def _serialize_approval(approval: ApprovalRecord) -> dict:
    return {
        "decision": approval.decision,
        "actor": approval.actor,
        "timestamp": approval.timestamp.isoformat(),
        "reason": approval.reason,
    }


def _serialize_event(event: LifecycleEvent) -> dict:
    return {
        "from_status": event.from_status.value if event.from_status is not None else None,
        "to_status": event.to_status.value,
        "timestamp": event.timestamp.isoformat(),
        "actor": event.actor,
        "reason": event.reason,
    }


def _deserialize_record(data: dict) -> TaskRecord:
    return TaskRecord(
        task_id=data["task_id"],
        project_id=data["project_id"],
        description=data["description"],
        status=TaskStatus(data["status"]),
        created_at=_parse_datetime(data["created_at"]),
        updated_at=_parse_datetime(data["updated_at"]),
        current_revision=data.get("current_revision"),
        plan_revisions=[
            _deserialize_revision(item) for item in data.get("plan_revisions", [])
        ],
        lifecycle_history=[
            _deserialize_event(item) for item in data.get("lifecycle_history", [])
        ],
    )


def _deserialize_revision(data: dict) -> PlanRevision:
    return PlanRevision(
        revision_number=data["revision_number"],
        created_at=_parse_datetime(data["created_at"]),
        status=data["status"],
        plan=_deserialize_plan(data["plan"]),
        approval=(
            _deserialize_approval(data["approval"])
            if data.get("approval") is not None
            else None
        ),
    )


def _deserialize_plan(data: dict) -> ImplementationPlan:
    return ImplementationPlan(
        summary=data["summary"],
        objectives=list(data.get("objectives", [])),
        requirements=list(data.get("requirements", [])),
        assumptions=[_deserialize_assumption(a) for a in data.get("assumptions", [])],
        unresolved_questions=list(data.get("unresolved_questions", [])),
        implementation_steps=[
            _deserialize_step(s) for s in data.get("implementation_steps", [])
        ],
        affected_components=[
            _deserialize_component(c) for c in data.get("affected_components", [])
        ],
        dependencies=[
            _deserialize_dependency(d) for d in data.get("dependencies", [])
        ],
        acceptance_criteria=list(data.get("acceptance_criteria", [])),
        testing_strategy=[
            _deserialize_testing(t) for t in data.get("testing_strategy", [])
        ],
        risks=[_deserialize_risk(r) for r in data.get("risks", [])],
        evidence=[_deserialize_evidence(e) for e in data.get("evidence", [])],
    )


def _deserialize_assumption(data: dict) -> PlanAssumption:
    return PlanAssumption(description=data["description"], reason=data["reason"])


def _deserialize_step(data: dict) -> ImplementationStep:
    return ImplementationStep(
        number=data["number"],
        description=data["description"],
        rationale=data["rationale"],
        affected_components=list(data.get("affected_components", [])),
        depends_on=list(data.get("depends_on", [])),
    )


def _deserialize_component(data: dict) -> AffectedComponent:
    return AffectedComponent(
        name=data["name"],
        path=data.get("path"),
        purpose=data["purpose"],
        evidence=list(data.get("evidence", [])),
    )


def _deserialize_dependency(data: dict) -> PlanDependency:
    return PlanDependency(
        name=data["name"],
        reason=data["reason"],
        existing=data.get("existing"),
    )


def _deserialize_testing(data: dict) -> TestingStrategyItem:
    return TestingStrategyItem(category=data["category"], description=data["description"])


def _deserialize_risk(data: dict) -> PlanRisk:
    return PlanRisk(
        description=data["description"],
        impact=data["impact"],
        mitigation=data["mitigation"],
    )


def _deserialize_evidence(data: dict) -> PlanEvidence:
    return PlanEvidence(
        source=data["source"],
        observation=data["observation"],
        supports=data["supports"],
    )


def _deserialize_approval(data: dict) -> ApprovalRecord:
    return ApprovalRecord(
        decision=data["decision"],
        actor=data["actor"],
        timestamp=_parse_datetime(data["timestamp"]),
        reason=data.get("reason"),
    )


def _deserialize_event(data: dict) -> LifecycleEvent:
    from_status_raw = data.get("from_status")
    return LifecycleEvent(
        from_status=(
            TaskStatus(from_status_raw) if from_status_raw is not None else None
        ),
        to_status=TaskStatus(data["to_status"]),
        timestamp=_parse_datetime(data["timestamp"]),
        actor=data.get("actor"),
        reason=data.get("reason"),
    )


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid datetime value: {value!r}") from exc
