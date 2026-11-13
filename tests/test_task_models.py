"""Tests for task domain models and exceptions."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

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
from factory.errors import (
    ActorResolutionError,
    FactoryLabError,
    InvalidTaskTransitionError,
    PlanValidationError,
    PlanningError,
    ProjectInspectionError,
    TaskError,
    TaskNotFoundError,
    TaskStorageError,
    TaskValidationError,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# TaskStatus enum
# ---------------------------------------------------------------------------

def test_task_status_has_six_values() -> None:
    assert {
        TaskStatus.CREATED,
        TaskStatus.PLANNING,
        TaskStatus.AWAITING_APPROVAL,
        TaskStatus.APPROVED,
        TaskStatus.REJECTED,
        TaskStatus.CANCELLED,
    } == set(TaskStatus)


def test_task_status_values_match_spec() -> None:
    assert TaskStatus.CREATED.value == "created"
    assert TaskStatus.PLANNING.value == "planning"
    assert TaskStatus.AWAITING_APPROVAL.value == "awaiting_approval"
    assert TaskStatus.APPROVED.value == "approved"
    assert TaskStatus.REJECTED.value == "rejected"
    assert TaskStatus.CANCELLED.value == "cancelled"


def test_task_status_is_string_enum() -> None:
    assert TaskStatus.CREATED == "created"
    assert "approved" in {s.value for s in TaskStatus}
    assert "failed" not in {s.value for s in TaskStatus}


# ---------------------------------------------------------------------------
# Plan-content frozen models
# ---------------------------------------------------------------------------

def test_plan_assumption_construction() -> None:
    assumption = PlanAssumption(
        description="existing architecture is preserved",
        reason="minimizes refactoring risk",
    )
    assert assumption.description == "existing architecture is preserved"
    assert assumption.reason == "minimizes refactoring risk"


def test_implementation_step_construction_with_defaults() -> None:
    step = ImplementationStep(
        number=1,
        description="Inspect existing implementation",
        rationale="identify extension points",
    )
    assert step.number == 1
    assert step.description == "Inspect existing implementation"
    assert step.rationale == "identify extension points"
    assert step.affected_components == []
    assert step.depends_on == []


def test_implementation_step_construction_with_all_fields() -> None:
    step = ImplementationStep(
        number=3,
        description="Implement requested functionality",
        rationale="deliver user-visible behavior",
        affected_components=["src/factory/cli/main.py"],
        depends_on=[1, 2],
    )
    assert step.number == 3
    assert step.affected_components == ["src/factory/cli/main.py"]
    assert step.depends_on == [1, 2]


def test_affected_component_construction() -> None:
    component = AffectedComponent(
        name="cli/main.py",
        path="src/factory/cli/main.py",
        purpose="adds task subcommands",
        evidence=["factory task create command"],
    )
    assert component.name == "cli/main.py"
    assert component.path == "src/factory/cli/main.py"
    assert component.purpose == "adds task subcommands"
    assert component.evidence == ["factory task create command"]


def test_affected_component_path_none() -> None:
    component = AffectedComponent(
        name="config module",
        path=None,
        purpose="reads configuration",
        evidence=[],
    )
    assert component.path is None


def test_plan_dependency_construction() -> None:
    dep = PlanDependency(name="typer", reason="CLI framework", existing=True)
    assert dep.name == "typer"
    assert dep.reason == "CLI framework"
    assert dep.existing is True


def test_plan_dependency_existing_none() -> None:
    dep = PlanDependency(name="unknown-pkg", reason="not yet evaluated", existing=None)
    assert dep.existing is None


def test_testing_strategy_item_construction() -> None:
    item = TestingStrategyItem(
        category="unit",
        description="test model constructors",
    )
    assert item.category == "unit"
    assert item.description == "test model constructors"


def test_plan_risk_construction() -> None:
    risk = PlanRisk(
        description="no tests exist for new code",
        impact="regressions go undetected",
        mitigation="add unit tests for every public function",
    )
    assert risk.description == "no tests exist for new code"
    assert risk.impact == "regressions go undetected"
    assert risk.mitigation == "add unit tests for every public function"


def test_plan_evidence_construction() -> None:
    evidence = PlanEvidence(
        source="pyproject.toml",
        observation="declares typer dependency",
        supports="CLI framework dependency",
    )
    assert evidence.source == "pyproject.toml"
    assert evidence.observation == "declares typer dependency"
    assert evidence.supports == "CLI framework dependency"


def test_implementation_plan_construction_with_minimal_fields() -> None:
    plan = ImplementationPlan(
        summary="Implement task intake",
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
    assert plan.summary == "Implement task intake"
    assert plan.objectives == []
    assert plan.requirements == []
    assert plan.implementation_steps == []


def test_implementation_plan_construction_with_all_fields() -> None:
    plan = ImplementationPlan(
        summary="Add task models",
        objectives=["define TaskStatus", "create TaskRecord"],
        requirements=["frozen plan content"],
        assumptions=[PlanAssumption(description="no DB yet", reason="M4 uses JSON")],
        unresolved_questions=["where to store tasks?"],
        implementation_steps=[
            ImplementationStep(
                number=1,
                description="write models",
                rationale="foundation for task service",
                affected_components=["task_models.py"],
                depends_on=[],
            )
        ],
        affected_components=[
            AffectedComponent(
                name="task_models.py",
                path="src/factory/control/task_models.py",
                purpose="domain models",
                evidence=["M4 spec Section 3"],
            )
        ],
        dependencies=[
            PlanDependency(name="python", reason="runtime", existing=True)
        ],
        acceptance_criteria=["all models construct correctly"],
        testing_strategy=[
            TestingStrategyItem(category="unit", description="test constructors")
        ],
        risks=[
            PlanRisk(
                description="missing field",
                impact="plan invalid",
                mitigation="validate before persistence",
            )
        ],
        evidence=[
            PlanEvidence(
                source="SPEC-M4.md",
                observation="defines all plan fields",
                supports="plan structure",
            )
        ],
    )
    assert len(plan.implementation_steps) == 1
    assert plan.implementation_steps[0].number == 1
    assert len(plan.affected_components) == 1
    assert len(plan.dependencies) == 1
    assert len(plan.risks) == 1
    assert len(plan.evidence) == 1


# ---------------------------------------------------------------------------
# Frozen behavior
# ---------------------------------------------------------------------------

def test_plan_assumption_is_frozen() -> None:
    assumption = PlanAssumption(description="x", reason="y")
    with pytest.raises(FrozenInstanceError):
        assumption.description = "changed"


def test_implementation_step_is_frozen() -> None:
    step = ImplementationStep(number=1, description="d", rationale="r")
    with pytest.raises(FrozenInstanceError):
        step.number = 2


def test_implementation_plan_is_frozen() -> None:
    plan = ImplementationPlan(
        summary="s",
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
    with pytest.raises(FrozenInstanceError):
        plan.summary = "changed"


def test_all_plan_content_models_are_frozen() -> None:
    """Every plan-content model must be frozen per SPEC-M4 Section 3."""
    # Each model is mutated on one of its own fields.
    frozen_cases = [
        (PlanAssumption(description="d", reason="r"), "description"),
        (ImplementationStep(number=1, description="d", rationale="r"), "description"),
        (AffectedComponent(name="n", path=None, purpose="p", evidence=[]), "name"),
        (PlanDependency(name="n", reason="r", existing=None), "name"),
        (TestingStrategyItem(category="c", description="d"), "category"),
        (PlanRisk(description="d", impact="i", mitigation="m"), "description"),
        (PlanEvidence(source="s", observation="o", supports="t"), "source"),
    ]
    for model, field_name in frozen_cases:
        with pytest.raises(FrozenInstanceError):
            setattr(model, field_name, "changed")


# ---------------------------------------------------------------------------
# ApprovalRecord
# ---------------------------------------------------------------------------

def test_approval_record_approved() -> None:
    approval = ApprovalRecord(
        decision="approved",
        actor="alice",
        timestamp=_now(),
    )
    assert approval.decision == "approved"
    assert approval.actor == "alice"
    assert approval.reason is None


def test_approval_record_rejected_with_reason() -> None:
    approval = ApprovalRecord(
        decision="rejected",
        actor="bob",
        timestamp=_now(),
        reason="plan lacks testing strategy",
    )
    assert approval.decision == "rejected"
    assert approval.actor == "bob"
    assert approval.reason == "plan lacks testing strategy"


# ---------------------------------------------------------------------------
# PlanRevision
# ---------------------------------------------------------------------------

def test_plan_revision_construction() -> None:
    plan = ImplementationPlan(
        summary="s",
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
    revision = PlanRevision(
        revision_number=1,
        created_at=_now(),
        status="awaiting_approval",
        plan=plan,
    )
    assert revision.revision_number == 1
    assert revision.status == "awaiting_approval"
    assert revision.plan is plan
    assert revision.approval is None


def test_plan_revision_with_approval() -> None:
    plan = ImplementationPlan(
        summary="s",
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
    approval = ApprovalRecord(
        decision="approved",
        actor="alice",
        timestamp=_now(),
    )
    revision = PlanRevision(
        revision_number=2,
        created_at=_now(),
        status="approved",
        plan=plan,
        approval=approval,
    )
    assert revision.revision_number == 2
    assert revision.status == "approved"
    assert revision.approval is approval
    assert revision.approval.decision == "approved"


# ---------------------------------------------------------------------------
# LifecycleEvent
# ---------------------------------------------------------------------------

def test_lifecycle_event_creation() -> None:
    event = LifecycleEvent(
        from_status=None,
        to_status=TaskStatus.CREATED,
        timestamp=_now(),
    )
    assert event.from_status is None
    assert event.to_status == TaskStatus.CREATED
    assert event.actor is None
    assert event.reason is None


def test_lifecycle_event_transition() -> None:
    event = LifecycleEvent(
        from_status=TaskStatus.CREATED,
        to_status=TaskStatus.PLANNING,
        timestamp=_now(),
        actor="alice",
        reason="user ran factory task plan",
    )
    assert event.from_status == TaskStatus.CREATED
    assert event.to_status == TaskStatus.PLANNING
    assert event.actor == "alice"
    assert event.reason == "user ran factory task plan"


# ---------------------------------------------------------------------------
# TaskRecord
# ---------------------------------------------------------------------------

def test_task_record_creation_defaults() -> None:
    task = TaskRecord(
        task_id="task_abc123",
        project_id="proj_1",
        description="Implement task models",
        status=TaskStatus.CREATED,
        created_at=_now(),
        updated_at=_now(),
    )
    assert task.task_id == "task_abc123"
    assert task.project_id == "proj_1"
    assert task.description == "Implement task models"
    assert task.status == TaskStatus.CREATED
    assert task.current_revision is None
    assert task.plan_revisions == []
    assert task.lifecycle_history == []


def test_task_record_with_revisions_and_history() -> None:
    plan = ImplementationPlan(
        summary="s",
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
    revision = PlanRevision(
        revision_number=1,
        created_at=_now(),
        status="approved",
        plan=plan,
    )
    event = LifecycleEvent(
        from_status=None,
        to_status=TaskStatus.CREATED,
        timestamp=_now(),
    )
    task = TaskRecord(
        task_id="task_abc123",
        project_id="proj_1",
        description="Implement task models",
        status=TaskStatus.APPROVED,
        created_at=_now(),
        updated_at=_now(),
        current_revision=1,
        plan_revisions=[revision],
        lifecycle_history=[event],
    )
    assert task.current_revision == 1
    assert len(task.plan_revisions) == 1
    assert task.plan_revisions[0] is revision
    assert len(task.lifecycle_history) == 1
    assert task.lifecycle_history[0] is event


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

def test_task_error_inherits_factory_lab_error() -> None:
    assert issubclass(TaskError, FactoryLabError)


def test_all_task_exceptions_inherit_from_task_error() -> None:
    exceptions = [
        TaskNotFoundError,
        TaskValidationError,
        InvalidTaskTransitionError,
        ProjectInspectionError,
        PlanningError,
        PlanValidationError,
        ActorResolutionError,
        TaskStorageError,
    ]
    for exc in exceptions:
        assert issubclass(exc, TaskError)


def test_task_not_found_error_is_task_error() -> None:
    err = TaskNotFoundError("task not found", detail="task_xyz")
    assert isinstance(err, TaskError)
    assert isinstance(err, FactoryLabError)
    assert err.message == "task not found"
    assert err.detail == "task_xyz"


def test_task_validation_error_is_task_error() -> None:
    err = TaskValidationError("invalid task id")
    assert isinstance(err, TaskError)
    assert isinstance(err, FactoryLabError)


def test_invalid_task_transition_error_is_task_error() -> None:
    err = InvalidTaskTransitionError("cannot plan an awaiting_approval task")
    assert isinstance(err, TaskError)
    assert isinstance(err, FactoryLabError)


def test_project_inspection_error_is_task_error() -> None:
    err = ProjectInspectionError("profiler failed")
    assert isinstance(err, TaskError)
    assert isinstance(err, FactoryLabError)


def test_planning_error_is_task_error() -> None:
    err = PlanningError("planner raised an exception")
    assert isinstance(err, TaskError)
    assert isinstance(err, FactoryLabError)


def test_plan_validation_error_is_task_error() -> None:
    err = PlanValidationError("step 3 depends on non-existent step 5")
    assert isinstance(err, TaskError)
    assert isinstance(err, FactoryLabError)


def test_actor_resolution_error_is_task_error() -> None:
    err = ActorResolutionError("could not resolve actor")
    assert isinstance(err, TaskError)
    assert isinstance(err, FactoryLabError)


def test_task_storage_error_is_task_error() -> None:
    err = TaskStorageError("corrupted JSON")
    assert isinstance(err, TaskError)
    assert isinstance(err, FactoryLabError)


def test_exception_chaining() -> None:
    try:
        raise TaskStorageError("failed to load task") from ValueError("underlying failure")
    except TaskStorageError as wrapped:
        assert isinstance(wrapped.__cause__, ValueError)
        assert str(wrapped.__cause__) == "underlying failure"
        assert isinstance(wrapped, TaskStorageError)
        assert isinstance(wrapped, TaskError)


def test_project_not_found_error_reused_from_m3() -> None:
    from factory.errors import ProjectNotFoundError

    assert issubclass(ProjectNotFoundError, FactoryLabError)
    # ProjectNotFoundError should NOT be a subclass of TaskError (it is reused
    # from M3 and inherits from ProjectError instead).
    assert not issubclass(ProjectNotFoundError, TaskError)
