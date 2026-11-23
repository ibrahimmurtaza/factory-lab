"""Tests for TaskService create, list, get, plan (M4-04, M4-05).

Task dependencies (TaskStorage, ProjectService, ProjectProfiler,
TaskPlanner, ActorResolver) are mocked so these tests exercise only the
service layer. No network, no external processes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from factory.control.planner import TaskPlanner
from factory.control.task import TaskService
from factory.control.task_models import (
    AffectedComponent,
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
from factory.errors import (
    ActorResolutionError,
    InvalidTaskTransitionError,
    PlanValidationError,
    PlanningError,
    ProjectInspectionError,
    ProjectNotFoundError,
    TaskNotFoundError,
    TaskValidationError,
)
from factory.intelligence.repository.models import (
    Detection,
    GitMetadata,
    ProjectProfile,
    RepositoryStructure,
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


# ---------------------------------------------------------------------------
# plan_task helpers
# ---------------------------------------------------------------------------

def _profile() -> ProjectProfile:
    return ProjectProfile(
        project_id="proj-1",
        project_name="test-proj",
        repository_root="/tmp/test-proj",
        inspected_at="2026-01-01T00:00:00+00:00",
        languages=[],
        frameworks=[],
        infrastructure=[],
        structure=RepositoryStructure(root="/tmp/test-proj"),
        git_metadata=None,
        detections=[],
    )


def _bad_plan(**overrides) -> ImplementationPlan:
    """Build an ImplementationPlan with optional field overrides."""
    data = dict(
        summary="bad plan",
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
    data.update(overrides)
    return ImplementationPlan(**data)


def _plan(summary="implement the feature") -> ImplementationPlan:
    return ImplementationPlan(
        summary=summary,
        objectives=["Implement the feature"],
        requirements=["Requirement 1"],
        assumptions=[],
        unresolved_questions=[],
        implementation_steps=[
            ImplementationStep(
                number=1,
                description="Implement feature",
                rationale="Needed for the task",
                affected_components=[],
                depends_on=[],
            )
        ],
        affected_components=[
            AffectedComponent(
                name="main.py",
                path="/tmp/test-proj/main.py",
                purpose="Feature implementation",
                evidence=[],
            )
        ],
        dependencies=[
            PlanDependency(name="fastapi", reason="API framework", existing=True)
        ],
        acceptance_criteria=["Feature works"],
        testing_strategy=[
            TestingStrategyItem(category="unit", description="Test feature")
        ],
        risks=[
            PlanRisk(
                description="Regression risk",
                impact="Medium",
                mitigation="Add tests",
            )
        ],
        evidence=[
            PlanEvidence(
                source="manifest",
                observation="fastapi detected",
                supports="dependency",
            )
        ],
    )


def _planning_record(
    task_id="task_abc123", project_id="proj-1", status=TaskStatus.CREATED
):
    return TaskRecord(
        task_id=task_id,
        project_id=project_id,
        description="implement the feature",
        status=status,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        current_revision=None,
    )


def _approved_record() -> TaskRecord:
    now = datetime.now(timezone.utc)
    plan = _plan()
    revision = PlanRevision(
        revision_number=1,
        created_at=now,
        status="approved",
        plan=plan,
        approval=None,
    )
    record = TaskRecord(
        task_id="task_abc123",
        project_id="proj-1",
        description="implement the feature",
        status=TaskStatus.APPROVED,
        created_at=now,
        updated_at=now,
        current_revision=1,
        plan_revisions=[revision],
    )
    record.lifecycle_history.append(
        LifecycleEvent(
            from_status=None,
            to_status=TaskStatus.CREATED,
            timestamp=now,
            actor=None,
        )
    )
    record.lifecycle_history.append(
        LifecycleEvent(
            from_status=TaskStatus.CREATED,
            to_status=TaskStatus.APPROVED,
            timestamp=now,
            actor=None,
        )
    )
    return record


# ---------------------------------------------------------------------------
# plan_task: created task
# ---------------------------------------------------------------------------


def test_plan_task_created_transitions_to_awaiting_approval():
    service, storage, project_service, profiler, planner, *_ = _make_service()
    storage.load.return_value = _planning_record(status=TaskStatus.CREATED)
    project_service.get_project.return_value = MagicMock(id="proj-1")
    profiler.profile.return_value = _profile()
    planner.create_plan.return_value = _plan()

    record = service.plan_task("task_abc123")

    assert record.status == TaskStatus.AWAITING_APPROVAL
    assert record.current_revision == 1
    assert len(record.plan_revisions) == 1
    assert record.plan_revisions[0].status == "awaiting_approval"


def test_plan_task_created_persists_via_storage():
    service, storage, project_service, profiler, planner, *_ = _make_service()
    storage.load.return_value = _planning_record(status=TaskStatus.CREATED)
    project_service.get_project.return_value = MagicMock(id="proj-1")
    profiler.profile.return_value = _profile()
    planner.create_plan.return_value = _plan()

    service.plan_task("task_abc123")

    storage.save.assert_called()
    saved_id, saved_record = storage.save.call_args[0]
    assert saved_id == "task_abc123"
    assert saved_record.status == TaskStatus.AWAITING_APPROVAL


def test_plan_task_created_records_planning_lifecycle_events():
    service, storage, project_service, profiler, planner, *_ = _make_service()
    storage.load.return_value = _planning_record(status=TaskStatus.CREATED)
    project_service.get_project.return_value = MagicMock(id="proj-1")
    profiler.profile.return_value = _profile()
    planner.create_plan.return_value = _plan()

    service.plan_task("task_abc123")

    statuses = [e.to_status for e in storage.save.call_args[0][1].lifecycle_history]
    assert TaskStatus.PLANNING in statuses
    assert TaskStatus.AWAITING_APPROVAL in statuses


# ---------------------------------------------------------------------------
# plan_task: rejected task (replan appends revision 2)
# ---------------------------------------------------------------------------


def test_plan_task_rejected_appends_revision_2():
    now = datetime.now(timezone.utc)
    rejected_plan = _plan(summary="original plan")
    revision_1 = PlanRevision(
        revision_number=1,
        created_at=now,
        status="rejected",
        plan=rejected_plan,
        approval=None,
    )
    record = TaskRecord(
        task_id="task_abc123",
        project_id="proj-1",
        description="implement the feature",
        status=TaskStatus.REJECTED,
        created_at=now,
        updated_at=now,
        current_revision=1,
        plan_revisions=[revision_1],
    )

    service, storage, project_service, profiler, planner, *_ = _make_service()
    storage.load.return_value = record
    project_service.get_project.return_value = MagicMock(id="proj-1")
    profiler.profile.return_value = _profile()
    planner.create_plan.return_value = _plan(summary="new plan")

    result = service.plan_task("task_abc123")

    assert result.status == TaskStatus.AWAITING_APPROVAL
    assert result.current_revision == 2
    assert len(result.plan_revisions) == 2
    assert result.plan_revisions[0].status == "rejected"
    assert result.plan_revisions[1].status == "awaiting_approval"


# ---------------------------------------------------------------------------
# plan_task: approved task — equivalent candidate retains revision
# ---------------------------------------------------------------------------


def test_plan_task_approved_equivalent_retains_revision():
    now = datetime.now(timezone.utc)
    same_plan = _plan(summary="same plan")
    revision_1 = PlanRevision(
        revision_number=1,
        created_at=now,
        status="approved",
        plan=same_plan,
        approval=None,
    )
    record = TaskRecord(
        task_id="task_abc123",
        project_id="proj-1",
        description="implement the feature",
        status=TaskStatus.APPROVED,
        created_at=now,
        updated_at=now,
        current_revision=1,
        plan_revisions=[revision_1],
    )

    service, storage, project_service, profiler, planner, *_ = _make_service()
    storage.load.return_value = record
    project_service.get_project.return_value = MagicMock(id="proj-1")
    profiler.profile.return_value = _profile()
    planner.create_plan.return_value = same_plan

    result = service.plan_task("task_abc123")

    assert result.status == TaskStatus.APPROVED
    assert result.current_revision == 1
    assert len(result.plan_revisions) == 1
    storage.save.assert_not_called()


# ---------------------------------------------------------------------------
# plan_task: approved task — materially different supersedes previous
# ---------------------------------------------------------------------------


def test_plan_task_approved_materially_different_supersedes():
    now = datetime.now(timezone.utc)
    old_plan = _plan(summary="old plan")
    new_plan = _plan(summary="new plan")
    revision_1 = PlanRevision(
        revision_number=1,
        created_at=now,
        status="approved",
        plan=old_plan,
        approval=None,
    )
    record = TaskRecord(
        task_id="task_abc123",
        project_id="proj-1",
        description="implement the feature",
        status=TaskStatus.APPROVED,
        created_at=now,
        updated_at=now,
        current_revision=1,
        plan_revisions=[revision_1],
    )

    service, storage, project_service, profiler, planner, *_ = _make_service()
    storage.load.return_value = record
    project_service.get_project.return_value = MagicMock(id="proj-1")
    profiler.profile.return_value = _profile()
    planner.create_plan.return_value = new_plan

    result = service.plan_task("task_abc123")

    assert result.status == TaskStatus.AWAITING_APPROVAL
    assert result.current_revision == 2
    assert len(result.plan_revisions) == 2
    assert result.plan_revisions[0].status == "superseded"
    assert result.plan_revisions[1].status == "awaiting_approval"


# ---------------------------------------------------------------------------
# plan_task: missing project
# ---------------------------------------------------------------------------


def test_plan_task_missing_project_raises():
    service, storage, project_service, profiler, planner, *_ = _make_service()
    storage.load.return_value = _planning_record(status=TaskStatus.CREATED)
    project_service.get_project.side_effect = ProjectNotFoundError(
        "Unknown project id: nope", detail="nope"
    )

    with pytest.raises(ProjectNotFoundError):
        service.plan_task("task_abc123")

    # Reverted to pre-planning state; save persists the rollback.
    saved_record = storage.save.call_args[0][1]
    assert saved_record.status == TaskStatus.CREATED


# ---------------------------------------------------------------------------
# plan_task: profiling failure preserves revisions
# ---------------------------------------------------------------------------


def test_plan_task_profiling_failure_preserves_revisions():
    now = datetime.now(timezone.utc)
    revision_1 = PlanRevision(
        revision_number=1,
        created_at=now,
        status="rejected",
        plan=_plan(),
        approval=None,
    )
    record = TaskRecord(
        task_id="task_abc123",
        project_id="proj-1",
        description="implement the feature",
        status=TaskStatus.REJECTED,
        created_at=now,
        updated_at=now,
        current_revision=1,
        plan_revisions=[revision_1],
    )

    service, storage, project_service, profiler, planner, *_ = _make_service()
    storage.load.return_value = record
    project_service.get_project.return_value = MagicMock(id="proj-1")
    profiler.profile.side_effect = RuntimeError("profiler down")

    with pytest.raises(ProjectInspectionError):
        service.plan_task("task_abc123")

    # Revisions preserved; task reverted to original status.
    assert record.status == TaskStatus.REJECTED
    assert len(record.plan_revisions) == 1
    storage.save.assert_called()


# ---------------------------------------------------------------------------
# plan_task: planner failure preserves revisions
# ---------------------------------------------------------------------------


def test_plan_task_planner_failure_preserves_revisions():
    now = datetime.now(timezone.utc)
    revision_1 = PlanRevision(
        revision_number=1,
        created_at=now,
        status="created",
        plan=_plan(),
        approval=None,
    )
    record = TaskRecord(
        task_id="task_abc123",
        project_id="proj-1",
        description="implement the feature",
        status=TaskStatus.CREATED,
        created_at=now,
        updated_at=now,
        current_revision=None,
        plan_revisions=[],
    )

    service, storage, project_service, profiler, planner, *_ = _make_service()
    storage.load.return_value = record
    project_service.get_project.return_value = MagicMock(id="proj-1")
    profiler.profile.return_value = _profile()
    planner.create_plan.side_effect = RuntimeError("planner down")

    with pytest.raises(PlanningError):
        service.plan_task("task_abc123")

    # No partial revision persisted.
    assert record.status == TaskStatus.CREATED
    assert record.current_revision is None
    assert len(record.plan_revisions) == 0
    storage.save.assert_called()


# ---------------------------------------------------------------------------
# plan_task: invalid transitions
# ---------------------------------------------------------------------------


def test_plan_task_awaiting_approval_rejected():
    service, storage, *_ = _make_service()
    record = _planning_record(status=TaskStatus.AWAITING_APPROVAL)
    storage.load.return_value = record

    with pytest.raises(InvalidTaskTransitionError):
        service.plan_task("task_abc123")

    storage.save.assert_not_called()


def test_plan_task_cancelled_rejected():
    service, storage, *_ = _make_service()
    record = _planning_record(status=TaskStatus.CANCELLED)
    storage.load.return_value = record

    with pytest.raises(InvalidTaskTransitionError):
        service.plan_task("task_abc123")

    storage.save.assert_not_called()


# ---------------------------------------------------------------------------
# plan_task: invalid plan rejected before persistence
# ---------------------------------------------------------------------------


def test_plan_task_invalid_plan_raises_plan_validation_error():
    service, storage, project_service, profiler, planner, *_ = _make_service()
    storage.load.return_value = _planning_record(status=TaskStatus.CREATED)
    project_service.get_project.return_value = MagicMock(id="proj-1")
    profiler.profile.return_value = _profile()

    bad_plan = _bad_plan(
        implementation_steps=[
            ImplementationStep(
                number=1,
                description="Step 1",
                rationale="Rationale",
                affected_components=[],
                depends_on=[2],  # references non-existent step
            )
        ]
    )
    planner.create_plan.return_value = bad_plan

    with pytest.raises(PlanValidationError):
        service.plan_task("task_abc123")

    # No revision persisted; save persists the rollback only.
    saved_record = storage.save.call_args[0][1]
    assert saved_record.status == TaskStatus.CREATED
    assert saved_record.current_revision is None
    assert len(saved_record.plan_revisions) == 0


# ---------------------------------------------------------------------------
# plan_task: self-dependency rejected
# ---------------------------------------------------------------------------


def test_plan_task_self_dependency_rejected():
    service, storage, project_service, profiler, planner, *_ = _make_service()
    storage.load.return_value = _planning_record(status=TaskStatus.CREATED)
    project_service.get_project.return_value = MagicMock(id="proj-1")
    profiler.profile.return_value = _profile()

    bad_plan = _bad_plan(
        implementation_steps=[
            ImplementationStep(
                number=1,
                description="Step 1",
                rationale="Rationale",
                affected_components=[],
                depends_on=[1],  # self-dependency
            )
        ]
    )
    planner.create_plan.return_value = bad_plan

    with pytest.raises(PlanValidationError):
        service.plan_task("task_abc123")

    saved_record = storage.save.call_args[0][1]
    assert saved_record.status == TaskStatus.CREATED
    assert len(saved_record.plan_revisions) == 0


# ---------------------------------------------------------------------------
# plan_task: duplicate step numbers rejected
# ---------------------------------------------------------------------------


def test_plan_task_duplicate_step_numbers_rejected():
    service, storage, project_service, profiler, planner, *_ = _make_service()
    storage.load.return_value = _planning_record(status=TaskStatus.CREATED)
    project_service.get_project.return_value = MagicMock(id="proj-1")
    profiler.profile.return_value = _profile()

    bad_plan = _bad_plan(
        implementation_steps=[
            ImplementationStep(
                number=1,
                description="Step 1",
                rationale="Rationale",
                affected_components=[],
                depends_on=[],
            ),
            ImplementationStep(
                number=1,
                description="Step 1 dup",
                rationale="Rationale",
                affected_components=[],
                depends_on=[],
            ),
        ]
    )
    planner.create_plan.return_value = bad_plan

    with pytest.raises(PlanValidationError):
        service.plan_task("task_abc123")

    saved_record = storage.save.call_args[0][1]
    assert saved_record.status == TaskStatus.CREATED
    assert len(saved_record.plan_revisions) == 0


# ---------------------------------------------------------------------------
# plan_task: empty summary rejected
# ---------------------------------------------------------------------------


def test_plan_task_empty_summary_rejected():
    service, storage, project_service, profiler, planner, *_ = _make_service()
    storage.load.return_value = _planning_record(status=TaskStatus.CREATED)
    project_service.get_project.return_value = MagicMock(id="proj-1")
    profiler.profile.return_value = _profile()

    bad_plan = _bad_plan(summary="")
    planner.create_plan.return_value = bad_plan

    with pytest.raises(PlanValidationError):
        service.plan_task("task_abc123")

    saved_record = storage.save.call_args[0][1]
    assert saved_record.status == TaskStatus.CREATED
    assert len(saved_record.plan_revisions) == 0


# ---------------------------------------------------------------------------
# plan_task: revision numbering increments sequentially
# ---------------------------------------------------------------------------


def test_plan_task_revision_numbering_increments():
    now = datetime.now(timezone.utc)
    revision_1 = PlanRevision(
        revision_number=1,
        created_at=now,
        status="rejected",
        plan=_plan(),
        approval=None,
    )
    revision_2 = PlanRevision(
        revision_number=2,
        created_at=now,
        status="awaiting_approval",
        plan=_plan(),
        approval=None,
    )
    record = TaskRecord(
        task_id="task_abc123",
        project_id="proj-1",
        description="implement the feature",
        status=TaskStatus.REJECTED,
        created_at=now,
        updated_at=now,
        current_revision=2,
        plan_revisions=[revision_1, revision_2],
    )

    service, storage, project_service, profiler, planner, *_ = _make_service()
    storage.load.return_value = record
    project_service.get_project.return_value = MagicMock(id="proj-1")
    profiler.profile.return_value = _profile()
    planner.create_plan.return_value = _plan(summary="third plan")

    result = service.plan_task("task_abc123")

    assert result.current_revision == 3
    assert len(result.plan_revisions) == 3
    assert result.plan_revisions[2].revision_number == 3


# ---------------------------------------------------------------------------
# plan_task: does not import detector implementations
# ---------------------------------------------------------------------------


def test_plan_task_uses_only_profiler_public_contract():
    """TaskService calls profiler.profile only; no detector internals."""
    service, storage, project_service, profiler, planner, *_ = _make_service()
    storage.load.return_value = _planning_record(status=TaskStatus.CREATED)
    project_service.get_project.return_value = MagicMock(id="proj-1")
    profiler.profile.return_value = _profile()
    planner.create_plan.return_value = _plan()

    service.plan_task("task_abc123")

    profiler.profile.assert_called_once_with("proj-1")
    planner.create_plan.assert_called_once()

    # Verify no detector-specific attributes are accessed on profiler.
    assert not any(
        "detector" in str(call).lower()
        for call in profiler.mock_calls
    )


# ---------------------------------------------------------------------------
# approve / reject / cancel helpers
# ---------------------------------------------------------------------------


def _awaiting_approval_record() -> TaskRecord:
    now = datetime.now(timezone.utc)
    plan = _plan()
    revision = PlanRevision(
        revision_number=1,
        created_at=now,
        status="awaiting_approval",
        plan=plan,
        approval=None,
    )
    record = TaskRecord(
        task_id="task_abc123",
        project_id="proj-1",
        description="implement the feature",
        status=TaskStatus.AWAITING_APPROVAL,
        created_at=now,
        updated_at=now,
        current_revision=1,
        plan_revisions=[revision],
    )
    record.lifecycle_history.append(
        LifecycleEvent(
            from_status=None,
            to_status=TaskStatus.CREATED,
            timestamp=now,
            actor=None,
        )
    )
    record.lifecycle_history.append(
        LifecycleEvent(
            from_status=TaskStatus.CREATED,
            to_status=TaskStatus.PLANNING,
            timestamp=now,
            actor=None,
        )
    )
    record.lifecycle_history.append(
        LifecycleEvent(
            from_status=TaskStatus.PLANNING,
            to_status=TaskStatus.AWAITING_APPROVAL,
            timestamp=now,
            actor=None,
        )
    )
    return record


# ---------------------------------------------------------------------------
# approve_task
# ---------------------------------------------------------------------------


def test_approve_task_transitions_to_approved():
    service, storage, project_service, profiler, planner, actor_resolver = (
        _make_service()
    )
    actor_resolver.resolve.return_value = "alice"
    storage.load.return_value = _awaiting_approval_record()

    record = service.approve_task("task_abc123")

    assert record.status == TaskStatus.APPROVED
    current_rev = record.plan_revisions[0]
    assert current_rev.status == "approved"
    assert current_rev.approval is not None
    assert current_rev.approval.decision == "approved"
    assert current_rev.approval.actor == "alice"
    assert current_rev.approval.reason is None
    actor_resolver.resolve.assert_called_once()
    storage.save.assert_called_once()


def test_approve_task_records_lifecycle_event():
    service, storage, project_service, profiler, planner, actor_resolver = (
        _make_service()
    )
    actor_resolver.resolve.return_value = "bob"
    storage.load.return_value = _awaiting_approval_record()

    service.approve_task("task_abc123")

    saved_record = storage.save.call_args[0][1]
    events = saved_record.lifecycle_history
    approve_events = [
        e for e in events if e.to_status == TaskStatus.APPROVED
    ]
    assert len(approve_events) == 1
    assert approve_events[0].from_status == TaskStatus.AWAITING_APPROVAL
    assert approve_events[0].actor == "bob"


def test_approve_task_unknown_task_raises():
    service, storage, *_ = _make_service()
    storage.load.return_value = None

    with pytest.raises(TaskNotFoundError):
        service.approve_task("task_missing")

    storage.save.assert_not_called()


def test_approve_task_not_awaiting_approval_raises():
    service, storage, *_ = _make_service()
    storage.load.return_value = _planning_record(status=TaskStatus.CREATED)

    with pytest.raises(InvalidTaskTransitionError):
        service.approve_task("task_abc123")

    storage.save.assert_not_called()


def test_approve_task_no_current_revision_raises():
    service, storage, project_service, profiler, planner, actor_resolver = (
        _make_service()
    )
    actor_resolver.resolve.return_value = "alice"
    now = datetime.now(timezone.utc)
    record = TaskRecord(
        task_id="task_abc123",
        project_id="proj-1",
        description="implement the feature",
        status=TaskStatus.AWAITING_APPROVAL,
        created_at=now,
        updated_at=now,
        current_revision=None,
        plan_revisions=[],
    )
    storage.load.return_value = record

    with pytest.raises(InvalidTaskTransitionError):
        service.approve_task("task_abc123")

    storage.save.assert_not_called()


def test_approve_task_actor_resolution_error():
    service, storage, *_unused, actor_resolver = _make_service()
    actor_resolver.resolve.side_effect = ActorResolutionError(
        "no actor", detail="none"
    )
    storage.load.return_value = _awaiting_approval_record()

    with pytest.raises(ActorResolutionError):
        service.approve_task("task_abc123")

    storage.save.assert_not_called()


# ---------------------------------------------------------------------------
# reject_task
# ---------------------------------------------------------------------------


def test_reject_task_transitions_to_rejected():
    service, storage, project_service, profiler, planner, actor_resolver = (
        _make_service()
    )
    actor_resolver.resolve.return_value = "carol"
    storage.load.return_value = _awaiting_approval_record()

    record = service.reject_task("task_abc123", "plan lacks tests")

    assert record.status == TaskStatus.REJECTED
    current_rev = record.plan_revisions[0]
    assert current_rev.status == "rejected"
    assert current_rev.approval is not None
    assert current_rev.approval.decision == "rejected"
    assert current_rev.approval.actor == "carol"
    assert current_rev.approval.reason == "plan lacks tests"
    actor_resolver.resolve.assert_called_once()
    storage.save.assert_called_once()


def test_reject_task_records_lifecycle_event_with_reason():
    service, storage, project_service, profiler, planner, actor_resolver = (
        _make_service()
    )
    actor_resolver.resolve.return_value = "dave"
    storage.load.return_value = _awaiting_approval_record()

    service.reject_task("task_abc123", "insufficient detail")

    saved_record = storage.save.call_args[0][1]
    events = saved_record.lifecycle_history
    reject_events = [
        e for e in events if e.to_status == TaskStatus.REJECTED
    ]
    assert len(reject_events) == 1
    assert reject_events[0].from_status == TaskStatus.AWAITING_APPROVAL
    assert reject_events[0].actor == "dave"
    assert reject_events[0].reason == "insufficient detail"


def test_reject_task_empty_reason_raises():
    service, *_ = _make_service()

    with pytest.raises(TaskValidationError):
        service.reject_task("task_abc123", "")

    with pytest.raises(TaskValidationError):
        service.reject_task("task_abc123", "   ")


def test_reject_task_unknown_task_raises():
    service, storage, *_ = _make_service()
    storage.load.return_value = None

    with pytest.raises(TaskNotFoundError):
        service.reject_task("task_missing", "reason")

    storage.save.assert_not_called()


def test_reject_task_not_awaiting_approval_raises():
    service, storage, *_ = _make_service()
    storage.load.return_value = _planning_record(status=TaskStatus.APPROVED)

    with pytest.raises(InvalidTaskTransitionError):
        service.reject_task("task_abc123", "reason")

    storage.save.assert_not_called()


def test_reject_task_no_current_revision_raises():
    service, storage, project_service, profiler, planner, actor_resolver = (
        _make_service()
    )
    actor_resolver.resolve.return_value = "eve"
    now = datetime.now(timezone.utc)
    record = TaskRecord(
        task_id="task_abc123",
        project_id="proj-1",
        description="implement the feature",
        status=TaskStatus.AWAITING_APPROVAL,
        created_at=now,
        updated_at=now,
        current_revision=None,
        plan_revisions=[],
    )
    storage.load.return_value = record

    with pytest.raises(InvalidTaskTransitionError):
        service.reject_task("task_abc123", "reason")

    storage.save.assert_not_called()


def test_reject_task_actor_resolution_error():
    service, storage, *_unused, actor_resolver = _make_service()
    actor_resolver.resolve.side_effect = ActorResolutionError(
        "no actor", detail="none"
    )
    storage.load.return_value = _awaiting_approval_record()

    with pytest.raises(ActorResolutionError):
        service.reject_task("task_abc123", "reason")

    storage.save.assert_not_called()


# ---------------------------------------------------------------------------
# cancel_task
# ---------------------------------------------------------------------------


def test_cancel_task_created_to_cancelled():
    service, storage, project_service, profiler, planner, actor_resolver = (
        _make_service()
    )
    actor_resolver.resolve.return_value = "frank"
    storage.load.return_value = _planning_record(status=TaskStatus.CREATED)

    record = service.cancel_task("task_abc123")

    assert record.status == TaskStatus.CANCELLED
    actor_resolver.resolve.assert_called_once()
    storage.save.assert_called_once()


def test_cancel_task_awaiting_approval_to_cancelled():
    service, storage, project_service, profiler, planner, actor_resolver = (
        _make_service()
    )
    actor_resolver.resolve.return_value = "grace"
    storage.load.return_value = _awaiting_approval_record()

    record = service.cancel_task("task_abc123")

    assert record.status == TaskStatus.CANCELLED


def test_cancel_task_approved_to_cancelled():
    service, storage, project_service, profiler, planner, actor_resolver = (
        _make_service()
    )
    actor_resolver.resolve.return_value = "heidi"
    storage.load.return_value = _approved_record()

    record = service.cancel_task("task_abc123")

    assert record.status == TaskStatus.CANCELLED


def test_cancel_task_rejected_to_cancelled():
    service, storage, project_service, profiler, planner, actor_resolver = (
        _make_service()
    )
    actor_resolver.resolve.return_value = "ivan"
    now = datetime.now(timezone.utc)
    plan = _plan()
    revision = PlanRevision(
        revision_number=1,
        created_at=now,
        status="rejected",
        plan=plan,
        approval=None,
    )
    record = TaskRecord(
        task_id="task_abc123",
        project_id="proj-1",
        description="implement the feature",
        status=TaskStatus.REJECTED,
        created_at=now,
        updated_at=now,
        current_revision=1,
        plan_revisions=[revision],
    )
    storage.load.return_value = record

    result = service.cancel_task("task_abc123")

    assert result.status == TaskStatus.CANCELLED


def test_cancel_task_planning_raises():
    service, storage, *_ = _make_service()
    storage.load.return_value = _planning_record(status=TaskStatus.PLANNING)

    with pytest.raises(InvalidTaskTransitionError):
        service.cancel_task("task_abc123")

    storage.save.assert_not_called()


def test_cancel_task_cancelled_raises():
    service, storage, *_ = _make_service()
    storage.load.return_value = _planning_record(status=TaskStatus.CANCELLED)

    with pytest.raises(InvalidTaskTransitionError):
        service.cancel_task("task_abc123")

    storage.save.assert_not_called()


def test_cancel_task_unknown_task_raises():
    service, storage, *_ = _make_service()
    storage.load.return_value = None

    with pytest.raises(TaskNotFoundError):
        service.cancel_task("task_missing")

    storage.save.assert_not_called()


def test_cancel_task_actor_resolution_error():
    service, storage, *_unused, actor_resolver = _make_service()
    actor_resolver.resolve.side_effect = ActorResolutionError(
        "no actor", detail="none"
    )
    storage.load.return_value = _awaiting_approval_record()

    with pytest.raises(ActorResolutionError):
        service.cancel_task("task_abc123")

    storage.save.assert_not_called()


def test_cancel_task_records_lifecycle_event():
    service, storage, project_service, profiler, planner, actor_resolver = (
        _make_service()
    )
    actor_resolver.resolve.return_value = "judy"
    storage.load.return_value = _planning_record(status=TaskStatus.APPROVED)

    service.cancel_task("task_abc123")

    saved_record = storage.save.call_args[0][1]
    events = saved_record.lifecycle_history
    cancel_events = [
        e for e in events if e.to_status == TaskStatus.CANCELLED
    ]
    assert len(cancel_events) == 1
    assert cancel_events[0].from_status == TaskStatus.APPROVED
    assert cancel_events[0].actor == "judy"


def test_cancel_task_invalid_transition_approve_created():
    service, storage, *_ = _make_service()
    storage.load.return_value = _planning_record(status=TaskStatus.CREATED)

    with pytest.raises(InvalidTaskTransitionError):
        service.approve_task("task_abc123")

    storage.save.assert_not_called()
