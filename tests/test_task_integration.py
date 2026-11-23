"""M4-10 integration and failure-path tests.

Uses real JsonTaskStorage + real TaskService backed by temporary directories,
with ProjectService/ProjectProfiler/TaskPlanner/ActorResolver mocked so no
real filesystem inspection or network access is required. These tests span
multiple M4 tickets (create -> plan -> approve/reject/cancel -> status -> show)
and verify failure-path preservation of revisions and approvals.

Does not duplicate unit tests from M4-01 through M4-08; focuses on
integration and cross-cutting validation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

import factory.cli.commands.task as task_cmd
from factory.cli.main import app
from factory.control.actor import ActorResolver
from factory.control.planner import DeterministicTaskPlanner
from factory.control.projects.service import ProjectService
from factory.control.task import TaskService
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
from factory.control.task_storage import JsonTaskStorage, default_tasks_dir
from factory.errors import (
    ActorResolutionError,
    InvalidTaskTransitionError,
    PlanValidationError,
    PlanningError,
    ProjectInspectionError,
    ProjectNotFoundError,
    TaskNotFoundError,
    TaskStorageError,
)
from factory.intelligence.repository.models import (
    Detection,
    GitMetadata,
    ProjectProfile,
    RepositoryStructure,
)


# ---------------------------------------------------------------------------
# Fixtures: real storage + real service, mocked external deps
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def tasks_dir(tmp_path: Path) -> Path:
    return tmp_path / "tasks"


@pytest.fixture
def storage(tasks_dir: Path) -> JsonTaskStorage:
    return JsonTaskStorage(tasks_dir)


@pytest.fixture
def project_profile() -> ProjectProfile:
    return ProjectProfile(
        project_id="proj-1",
        project_name="test-proj",
        repository_root="/tmp/test-proj",
        inspected_at="2026-01-01T00:00:00+00:00",
        languages=[Detection("Python", "language", [])],
        frameworks=[Detection("FastAPI", "framework", [])],
        infrastructure=[],
        structure=RepositoryStructure(root="/tmp/test-proj"),
        git_metadata=None,
        detections=[],
    )


@pytest.fixture
def implementation_plan() -> ImplementationPlan:
    return ImplementationPlan(
        summary="implement the feature",
        objectives=["Implement the feature"],
        requirements=["Requirement 1"],
        assumptions=[
            PlanAssumption("existing architecture preserved", "no refactor needed")
        ],
        unresolved_questions=["How to handle edge cases?"],
        implementation_steps=[
            ImplementationStep(
                number=1,
                description="Inspect existing implementation",
                rationale="Find extension points",
                affected_components=["main.py"],
                depends_on=[],
            )
        ],
        affected_components=[
            AffectedComponent(
                name="main.py",
                path="/tmp/test-proj/main.py",
                purpose="Feature implementation",
                evidence=["source dir"],
            )
        ],
        dependencies=[
            PlanDependency("fastapi", "API framework", existing=True)
        ],
        acceptance_criteria=["Feature works"],
        testing_strategy=[
            TestingStrategyItem("unit", "Test feature")
        ],
        risks=[
            PlanRisk("Regression risk", "Medium", "Add tests")
        ],
        evidence=[
            PlanEvidence("manifest", "fastapi detected", "dependency")
        ],
    )


@pytest.fixture
def real_service(
    storage: JsonTaskStorage,
    project_profile: ProjectProfile,
    implementation_plan: ImplementationPlan,
    monkeypatch,
) -> TaskService:
    """Build a real TaskService with real storage and mocked external deps."""
    project_service = MagicMock(spec=ProjectService)
    project_service.get_project.return_value = MagicMock(id="proj-1")

    profiler = MagicMock()
    profiler.profile.return_value = project_profile

    planner = MagicMock(spec=DeterministicTaskPlanner)
    planner.create_plan.return_value = implementation_plan

    actor_resolver = MagicMock(spec=ActorResolver)
    actor_resolver.resolve.return_value = "alice"

    return TaskService(
        storage=storage,
        project_service=project_service,
        profiler=profiler,
        planner=planner,
        actor_resolver=actor_resolver,
    )


# ---------------------------------------------------------------------------
# End-to-end flows (real storage, real TaskService)
# ---------------------------------------------------------------------------


def test_create_then_plan_then_approve_end_to_end(
    real_service: TaskService, storage: JsonTaskStorage
):
    record = real_service.create_task("proj-1", "implement the feature")
    assert record.status == TaskStatus.CREATED
    assert record.current_revision is None

    planned = real_service.plan_task(record.task_id)
    assert planned.status == TaskStatus.AWAITING_APPROVAL
    assert planned.current_revision == 1

    approved = real_service.approve_task(record.task_id)
    assert approved.status == TaskStatus.APPROVED
    assert approved.plan_revisions[0].status == "approved"
    assert approved.plan_revisions[0].approval is not None
    assert approved.plan_revisions[0].approval.decision == "approved"
    assert approved.plan_revisions[0].approval.actor == "alice"

    # Persistence verified via real storage.
    loaded = storage.load(record.task_id)
    assert loaded is not None
    assert loaded.status == TaskStatus.APPROVED
    assert loaded.current_revision == 1


def test_create_then_plan_then_reject_end_to_end(
    real_service: TaskService, storage: JsonTaskStorage
):
    record = real_service.create_task("proj-1", "implement the feature")
    planned = real_service.plan_task(record.task_id)
    assert planned.status == TaskStatus.AWAITING_APPROVAL

    rejected = real_service.reject_task(record.task_id, "plan lacks tests")
    assert rejected.status == TaskStatus.REJECTED
    assert rejected.plan_revisions[0].status == "rejected"
    assert rejected.plan_revisions[0].approval.reason == "plan lacks tests"

    loaded = storage.load(record.task_id)
    assert loaded.status == TaskStatus.REJECTED


def test_create_then_plan_then_cancel_end_to_end(
    real_service: TaskService, storage: JsonTaskStorage
):
    record = real_service.create_task("proj-1", "implement the feature")
    planned = real_service.plan_task(record.task_id)
    assert planned.status == TaskStatus.AWAITING_APPROVAL

    cancelled = real_service.cancel_task(record.task_id)
    assert cancelled.status == TaskStatus.CANCELLED

    loaded = storage.load(record.task_id)
    assert loaded.status == TaskStatus.CANCELLED


def test_reject_then_replan_then_approve_end_to_end(
    real_service: TaskService, storage: JsonTaskStorage
):
    record = real_service.create_task("proj-1", "implement the feature")
    real_service.plan_task(record.task_id)
    real_service.reject_task(record.task_id, "needs work")

    # Replan after rejection appends revision 2.
    replanned = real_service.plan_task(record.task_id)
    assert replanned.status == TaskStatus.AWAITING_APPROVAL
    assert replanned.current_revision == 2
    assert len(replanned.plan_revisions) == 2
    assert replanned.plan_revisions[0].status == "rejected"
    assert replanned.plan_revisions[1].status == "awaiting_approval"

    approved = real_service.approve_task(record.task_id)
    assert approved.status == TaskStatus.APPROVED
    assert approved.current_revision == 2
    assert approved.plan_revisions[1].status == "approved"

    loaded = storage.load(record.task_id)
    assert loaded.current_revision == 2
    assert len(loaded.plan_revisions) == 2


def test_approved_then_replan_then_approve_end_to_end(
    real_service: TaskService, storage: JsonTaskStorage
):
    record = real_service.create_task("proj-1", "implement the feature")
    real_service.plan_task(record.task_id)
    real_service.approve_task(record.task_id)

    # Materially different plan supersedes revision 1.
    different_plan = ImplementationPlan(
        summary="implement the feature differently",
        objectives=["Implement differently"],
        requirements=[],
        assumptions=[],
        unresolved_questions=[],
        implementation_steps=[
            ImplementationStep(
                number=1,
                description="Redesign from scratch",
                rationale="New approach",
                affected_components=[],
                depends_on=[],
            )
        ],
        affected_components=[],
        dependencies=[],
        acceptance_criteria=[],
        testing_strategy=[],
        risks=[],
        evidence=[],
    )
    real_service._planner.create_plan.return_value = different_plan

    replanned = real_service.plan_task(record.task_id)
    assert replanned.status == TaskStatus.AWAITING_APPROVAL
    assert replanned.current_revision == 2
    assert len(replanned.plan_revisions) == 2
    assert replanned.plan_revisions[0].status == "superseded"
    assert replanned.plan_revisions[0].approval is not None  # approval retained
    assert replanned.plan_revisions[1].status == "awaiting_approval"

    loaded = storage.load(record.task_id)
    assert loaded.plan_revisions[0].status == "superseded"
    assert loaded.plan_revisions[0].approval is not None


def test_status_and_show_after_approve(
    real_service: TaskService, storage: JsonTaskStorage
):
    record = real_service.create_task("proj-1", "implement the feature")
    real_service.plan_task(record.task_id)
    real_service.approve_task(record.task_id)

    status_record = real_service.get_task(record.task_id)
    assert status_record.status == TaskStatus.APPROVED

    show_record = real_service.get_task(record.task_id)
    assert show_record.plan_revisions[0].approval is not None
    assert len(show_record.lifecycle_history) >= 2


# ---------------------------------------------------------------------------
# Failure-path tests with real storage
# ---------------------------------------------------------------------------


def test_planning_failure_preserves_revisions_and_status(
    real_service: TaskService,
    storage: JsonTaskStorage,
    project_profile: ProjectProfile,
    monkeypatch,
):
    record = real_service.create_task("proj-1", "implement the feature")
    real_service.plan_task(record.task_id)
    real_service.approve_task(record.task_id)

    # Planner now raises on replanning -> wrapped as PlanningError.
    real_service._planner.create_plan.side_effect = RuntimeError("planner down")

    with pytest.raises(PlanningError):
        real_service.plan_task(record.task_id)

    # Persisted state unchanged: still approved, revision 1 preserved.
    loaded = storage.load(record.task_id)
    assert loaded.status == TaskStatus.APPROVED
    assert loaded.current_revision == 1
    assert len(loaded.plan_revisions) == 1
    assert loaded.plan_revisions[0].status == "approved"


def test_profiling_failure_preserves_revisions(
    real_service: TaskService,
    storage: JsonTaskStorage,
    monkeypatch,
):
    record = real_service.create_task("proj-1", "implement the feature")
    real_service.plan_task(record.task_id)
    real_service.reject_task(record.task_id, "rejected")

    real_service._profiler.profile.side_effect = ProjectInspectionError(
        "profiler down", detail="none"
    )

    with pytest.raises(ProjectInspectionError):
        real_service.plan_task(record.task_id)

    loaded = storage.load(record.task_id)
    assert loaded.status == TaskStatus.REJECTED
    assert len(loaded.plan_revisions) == 1
    assert loaded.plan_revisions[0].status == "rejected"


def test_invalid_plan_not_persisted(
    real_service: TaskService,
    storage: JsonTaskStorage,
    monkeypatch,
):
    record = real_service.create_task("proj-1", "implement the feature")

    bad_plan = ImplementationPlan(
        summary="",  # empty summary -> validation error
        objectives=[],
        requirements=[],
        assumptions=[],
        unresolved_questions=[],
        implementation_steps=[],
        affected_components=[],
        dependencies=[],
        acceptance_criteria=[],
        testing_strategy=[],
        risks=[],
        evidence=[],
    )
    real_service._planner.create_plan.return_value = bad_plan

    with pytest.raises(PlanValidationError):
        real_service.plan_task(record.task_id)

    loaded = storage.load(record.task_id)
    assert loaded.status == TaskStatus.CREATED
    assert loaded.current_revision is None
    assert len(loaded.plan_revisions) == 0


def test_plan_on_awaiting_approval_rejected_without_mutation(
    real_service: TaskService, storage: JsonTaskStorage
):
    record = real_service.create_task("proj-1", "implement the feature")
    real_service.plan_task(record.task_id)
    # status is now awaiting_approval

    with pytest.raises(InvalidTaskTransitionError):
        real_service.plan_task(record.task_id)

    loaded = storage.load(record.task_id)
    assert loaded.status == TaskStatus.AWAITING_APPROVAL
    assert len(loaded.plan_revisions) == 1


def test_plan_on_cancelled_task_rejected(
    real_service: TaskService, storage: JsonTaskStorage
):
    record = real_service.create_task("proj-1", "implement the feature")
    real_service.cancel_task(record.task_id)

    with pytest.raises(InvalidTaskTransitionError):
        real_service.plan_task(record.task_id)

    loaded = storage.load(record.task_id)
    assert loaded.status == TaskStatus.CANCELLED


def test_cancel_from_planning_rejected(
    real_service: TaskService, storage: JsonTaskStorage, monkeypatch
):
    record = real_service.create_task("proj-1", "implement the feature")
    real_service.cancel_task(record.task_id)

    with pytest.raises(InvalidTaskTransitionError):
        real_service.cancel_task(record.task_id)

    loaded = storage.load(record.task_id)
    assert loaded.status == TaskStatus.CANCELLED


# ---------------------------------------------------------------------------
# Corrupted storage handling
# ---------------------------------------------------------------------------


def test_corrupted_storage_load_raises_task_storage_error(
    storage: JsonTaskStorage, tmp_path: Path
):
    storage.save("task_bad", TaskRecord(
        task_id="task_bad",
        project_id="proj-1",
        description="x",
        status=TaskStatus.CREATED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ))
    # Corrupt the file on disk.
    path = storage._directory / "task_bad.json"
    path.write_text("{ not valid json", encoding="utf-8")

    service = TaskService(
        storage=storage,
        project_service=MagicMock(),
        profiler=MagicMock(),
        planner=MagicMock(),
        actor_resolver=MagicMock(),
    )

    with pytest.raises(TaskStorageError):
        service.get_task("task_bad")


def test_corrupted_storage_list_all_raises(
    storage: JsonTaskStorage,
):
    storage.save("task_good", TaskRecord(
        task_id="task_good",
        project_id="proj-1",
        description="x",
        status=TaskStatus.CREATED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ))
    bad_path = storage._directory / "task_bad.json"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("{ not valid json", encoding="utf-8")

    service = TaskService(
        storage=storage,
        project_service=MagicMock(),
        profiler=MagicMock(),
        planner=MagicMock(),
        actor_resolver=MagicMock(),
    )

    with pytest.raises(TaskStorageError):
        service.list_tasks()


# ---------------------------------------------------------------------------
# Actor resolution failure in integration
# ---------------------------------------------------------------------------


def test_actor_resolution_error_prevents_approval(
    storage: JsonTaskStorage,
    monkeypatch,
):
    project_service = MagicMock()
    project_service.get_project.return_value = MagicMock(id="proj-1")
    profiler = MagicMock()
    profiler.profile.return_value = ProjectProfile(
        project_id="proj-1",
        project_name="p",
        repository_root="/tmp/p",
        inspected_at="2026-01-01T00:00:00+00:00",
        languages=[],
        frameworks=[],
        infrastructure=[],
        structure=RepositoryStructure(root="/tmp/p"),
        git_metadata=None,
        detections=[],
    )
    planner = MagicMock()
    planner.create_plan.return_value = ImplementationPlan(
        summary="x", objectives=[], requirements=[], assumptions=[],
        unresolved_questions=[], implementation_steps=[], affected_components=[],
        dependencies=[], acceptance_criteria=[], testing_strategy=[],
        risks=[], evidence=[],
    )
    actor_resolver = MagicMock(spec=ActorResolver)
    actor_resolver.resolve.side_effect = ActorResolutionError(
        "no actor", detail="none"
    )

    service = TaskService(
        storage=storage,
        project_service=project_service,
        profiler=profiler,
        planner=planner,
        actor_resolver=actor_resolver,
    )

    record = service.create_task("proj-1", "implement the feature")
    service.plan_task(record.task_id)

    with pytest.raises(ActorResolutionError):
        service.approve_task(record.task_id)

    # No state transition occurred.
    loaded = storage.load(record.task_id)
    assert loaded.status == TaskStatus.AWAITING_APPROVAL
    assert loaded.plan_revisions[0].approval is None


# ---------------------------------------------------------------------------
# CLI end-to-end integration: real service, real storage, monkeypatched _task_service
# ---------------------------------------------------------------------------


def test_cli_create_plan_approve_status_show_sequence(
    runner: CliRunner,
    tasks_dir: Path,
    project_profile: ProjectProfile,
    implementation_plan: ImplementationPlan,
    monkeypatch,
):
    """Run multiple factory task commands in sequence against real storage."""
    monkeypatch.setattr(task_cmd, "default_tasks_dir", lambda: tasks_dir)

    project_service = MagicMock()
    project_service.get_project.return_value = MagicMock(id="proj-1")
    profiler = MagicMock()
    profiler.profile.return_value = project_profile
    planner = MagicMock()
    planner.create_plan.return_value = implementation_plan
    actor_resolver = MagicMock(spec=ActorResolver)
    actor_resolver.resolve.return_value = "alice"

    service = TaskService(
        storage=JsonTaskStorage(tasks_dir),
        project_service=project_service,
        profiler=profiler,
        planner=planner,
        actor_resolver=actor_resolver,
    )
    monkeypatch.setattr(task_cmd, "_task_service", lambda: service)

    # create
    result = runner.invoke(app, ["task", "create", "proj-1", "implement the feature"])
    assert result.exit_code == 0
    task_id = [line for line in result.output.splitlines() if line.startswith("Task created:")][0]
    task_id = task_id.split(": ")[1].strip()

    # plan
    result = runner.invoke(app, ["task", "plan", task_id])
    assert result.exit_code == 0
    assert "awaiting_approval" in result.output

    # approve
    result = runner.invoke(app, ["task", "approve", task_id])
    assert result.exit_code == 0
    assert "approved" in result.output.lower()

    # status
    result = runner.invoke(app, ["task", "status", task_id])
    assert result.exit_code == 0
    assert task_id in result.output
    assert "approved" in result.output

    # show
    result = runner.invoke(app, ["task", "show", task_id])
    assert result.exit_code == 0
    assert task_id in result.output
    assert "proj-1" in result.output
    assert "alice" in result.output


def test_cli_invalid_transition_exit_1_with_real_service(
    runner: CliRunner,
    tasks_dir: Path,
    project_profile: ProjectProfile,
    implementation_plan: ImplementationPlan,
    monkeypatch,
):
    monkeypatch.setattr(task_cmd, "default_tasks_dir", lambda: tasks_dir)

    service = TaskService(
        storage=JsonTaskStorage(tasks_dir),
        project_service=MagicMock(get_project=MagicMock(return_value=MagicMock(id="proj-1"))),
        profiler=MagicMock(profile=MagicMock(return_value=project_profile)),
        planner=MagicMock(create_plan=MagicMock(return_value=implementation_plan)),
        actor_resolver=MagicMock(resolve=MagicMock(return_value="alice")),
    )
    monkeypatch.setattr(task_cmd, "_task_service", lambda: service)

    service.create_task("proj-1", "implement the feature")

    # Approve a created task (not awaiting_approval) -> invalid transition.
    result = runner.invoke(app, ["task", "approve", service.list_tasks()[0].task_id])
    assert result.exit_code == 1
    assert "Cannot approve" in result.output


def test_cli_missing_task_exit_1(
    runner: CliRunner,
    tasks_dir: Path,
    monkeypatch,
):
    monkeypatch.setattr(task_cmd, "default_tasks_dir", lambda: tasks_dir)

    service = TaskService(
        storage=JsonTaskStorage(tasks_dir),
        project_service=MagicMock(),
        profiler=MagicMock(),
        planner=MagicMock(),
        actor_resolver=MagicMock(),
    )
    monkeypatch.setattr(task_cmd, "_task_service", lambda: service)

    result = runner.invoke(app, ["task", "status", "task_missing"])
    assert result.exit_code == 1
    assert "Unknown task id" in result.output


def test_cli_task_service_is_monkeypatchable(
    runner: CliRunner,
    tasks_dir: Path,
    monkeypatch,
):
    """Verify _task_service can be replaced with a real service backed by temp storage."""
    monkeypatch.setattr(task_cmd, "default_tasks_dir", lambda: tasks_dir)

    service = TaskService(
        storage=JsonTaskStorage(tasks_dir),
        project_service=MagicMock(),
        profiler=MagicMock(),
        planner=MagicMock(),
        actor_resolver=MagicMock(),
    )
    monkeypatch.setattr(task_cmd, "_task_service", lambda: service)

    result = runner.invoke(app, ["task", "list"])
    assert result.exit_code == 0
    assert "No tasks registered" in result.output

