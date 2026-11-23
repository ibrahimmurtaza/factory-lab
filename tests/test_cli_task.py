"""CLI integration tests for factory task commands (M4-08).

Uses temporary directories and a monkeypatched _task_service so no real
filesystem or network access is required. Tests all 8 commands, exit codes
(0, 1, 2), and user-facing error messages.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

import factory.cli.commands.task as task_cmd
from factory.cli.main import app
from factory.control.task_models import (
    ApprovalRecord,
    ImplementationPlan,
    ImplementationStep,
    LifecycleEvent,
    PlanRevision,
    TaskRecord,
    TaskStatus,
)
from factory.errors import (
    FactoryLabError,
    InvalidTaskTransitionError,
    ProjectNotFoundError,
    TaskNotFoundError,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def isolated_tasks_dir(tmp_path, monkeypatch):
    """Point the task storage at a temporary directory."""
    target = tmp_path / "tasks"
    monkeypatch.setattr(task_cmd, "default_tasks_dir", lambda: target)
    return target


@pytest.fixture
def mock_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def monkeypatched_service(monkeypatch, mock_service):
    """Replace _task_service with a mock returning mock_service."""
    monkeypatch.setattr(task_cmd, "_task_service", lambda: mock_service)
    return mock_service


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


def test_task_create_success(runner, isolated_tasks_dir, monkeypatched_service):
    record = TaskRecord(
        task_id="task_abc123",
        project_id="proj-1",
        description="implement the feature",
        status=TaskStatus.CREATED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        current_revision=None,
    )
    monkeypatched_service.create_task.return_value = record

    result = runner.invoke(app, ["task", "create", "proj-1", "implement the feature"])

    assert result.exit_code == 0
    assert "task_abc123" in result.output
    monkeypatched_service.create_task.assert_called_once_with("proj-1", "implement the feature")


def test_task_create_missing_args_exit_2(runner, isolated_tasks_dir):
    result = runner.invoke(app, ["task", "create", "proj-1"])
    assert result.exit_code == 2


def test_task_create_empty_project_id_exit_2(runner, isolated_tasks_dir, monkeypatched_service):
    result = runner.invoke(app, ["task", "create", "", "implement the feature"])
    assert result.exit_code == 2
    monkeypatched_service.create_task.assert_not_called()


def test_task_create_empty_description_exit_2(runner, isolated_tasks_dir, monkeypatched_service):
    result = runner.invoke(app, ["task", "create", "proj-1", ""])
    assert result.exit_code == 2
    monkeypatched_service.create_task.assert_not_called()


def test_task_create_project_not_found_exit_1(runner, isolated_tasks_dir, monkeypatched_service):
    monkeypatched_service.create_task.side_effect = ProjectNotFoundError(
        "Unknown project id: nope", detail="nope"
    )
    result = runner.invoke(app, ["task", "create", "nope", "implement the feature"])
    assert result.exit_code == 1
    assert "Unknown project id" in result.output


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_task_list_success(runner, isolated_tasks_dir, monkeypatched_service):
    records = [
        TaskRecord(
            task_id="task_aaa",
            project_id="proj-1",
            description="task a",
            status=TaskStatus.CREATED,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        TaskRecord(
            task_id="task_bbb",
            project_id="proj-2",
            description="task b",
            status=TaskStatus.APPROVED,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    ]
    monkeypatched_service.list_tasks.return_value = records

    result = runner.invoke(app, ["task", "list"])

    assert result.exit_code == 0
    assert "task_aaa" in result.output
    assert "task_bbb" in result.output
    assert "proj-1" in result.output


def test_task_list_empty(runner, isolated_tasks_dir, monkeypatched_service):
    monkeypatched_service.list_tasks.return_value = []

    result = runner.invoke(app, ["task", "list"])

    assert result.exit_code == 0
    assert "No tasks registered" in result.output


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_task_status_success(runner, isolated_tasks_dir, monkeypatched_service):
    record = TaskRecord(
        task_id="task_abc123",
        project_id="proj-1",
        description="implement the feature",
        status=TaskStatus.AWAITING_APPROVAL,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        current_revision=1,
    )
    revision = PlanRevision(
        revision_number=1,
        created_at=datetime.now(timezone.utc),
        status="awaiting_approval",
        plan=ImplementationPlan(
            summary="implement the feature",
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
        ),
    )
    record.plan_revisions = [revision]
    monkeypatched_service.get_task.return_value = record

    result = runner.invoke(app, ["task", "status", "task_abc123"])

    assert result.exit_code == 0
    assert "task_abc123" in result.output
    assert "awaiting_approval" in result.output


def test_task_status_unknown_task_exit_1(runner, isolated_tasks_dir, monkeypatched_service):
    monkeypatched_service.get_task.side_effect = TaskNotFoundError(
        "Unknown task id: task_missing", detail="task_missing"
    )
    result = runner.invoke(app, ["task", "status", "task_missing"])
    assert result.exit_code == 1
    assert "Unknown task id" in result.output


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def test_task_show_success(runner, isolated_tasks_dir, monkeypatched_service):
    record = TaskRecord(
        task_id="task_abc123",
        project_id="proj-1",
        description="implement the feature",
        status=TaskStatus.APPROVED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        current_revision=1,
        plan_revisions=[
            PlanRevision(
                revision_number=1,
                created_at=datetime.now(timezone.utc),
                status="approved",
                plan=ImplementationPlan(
                    summary="implement the feature",
                    objectives=["Implement the feature"],
                    requirements=[],
                    assumptions=[],
                    unresolved_questions=[],
                    implementation_steps=[
                        ImplementationStep(
                            number=1,
                            description="Implement feature",
                            rationale="Needed",
                            affected_components=[],
                            depends_on=[],
                        )
                    ],
                    affected_components=[],
                    dependencies=[],
                    acceptance_criteria=["Feature works"],
                    testing_strategy=[],
                    risks=[],
                    evidence=[],
                ),
                approval=ApprovalRecord(
                    decision="approved",
                    actor="alice",
                    timestamp=datetime.now(timezone.utc),
                ),
            )
        ],
        lifecycle_history=[
            LifecycleEvent(
                from_status=None,
                to_status=TaskStatus.CREATED,
                timestamp=datetime.now(timezone.utc),
            ),
            LifecycleEvent(
                from_status=TaskStatus.CREATED,
                to_status=TaskStatus.APPROVED,
                timestamp=datetime.now(timezone.utc),
                actor="alice",
            ),
        ],
    )
    monkeypatched_service.get_task.return_value = record

    result = runner.invoke(app, ["task", "show", "task_abc123"])

    assert result.exit_code == 0
    assert "task_abc123" in result.output
    assert "proj-1" in result.output
    assert "implement the feature" in result.output
    assert "approved" in result.output
    assert "alice" in result.output


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


def test_task_plan_success(runner, isolated_tasks_dir, monkeypatched_service):
    record = TaskRecord(
        task_id="task_abc123",
        project_id="proj-1",
        description="implement the feature",
        status=TaskStatus.AWAITING_APPROVAL,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        current_revision=1,
    )
    monkeypatched_service.plan_task.return_value = record

    result = runner.invoke(app, ["task", "plan", "task_abc123"])

    assert result.exit_code == 0
    assert "task_abc123" in result.output
    monkeypatched_service.plan_task.assert_called_once_with("task_abc123")


def test_task_plan_invalid_transition_exit_1(runner, isolated_tasks_dir, monkeypatched_service):
    monkeypatched_service.plan_task.side_effect = InvalidTaskTransitionError(
        "Cannot plan task in awaiting_approval state",
        detail="Approve or reject first",
    )
    result = runner.invoke(app, ["task", "plan", "task_abc123"])
    assert result.exit_code == 1
    assert "Cannot plan task" in result.output


# ---------------------------------------------------------------------------
# approve
# ---------------------------------------------------------------------------


def test_task_approve_success(runner, isolated_tasks_dir, monkeypatched_service):
    record = TaskRecord(
        task_id="task_abc123",
        project_id="proj-1",
        description="implement the feature",
        status=TaskStatus.APPROVED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        current_revision=1,
    )
    monkeypatched_service.approve_task.return_value = record

    result = runner.invoke(app, ["task", "approve", "task_abc123"])

    assert result.exit_code == 0
    assert "approved" in result.output.lower()
    monkeypatched_service.approve_task.assert_called_once_with("task_abc123")


def test_task_approve_invalid_transition_exit_1(runner, isolated_tasks_dir, monkeypatched_service):
    monkeypatched_service.approve_task.side_effect = InvalidTaskTransitionError(
        "Cannot approve task in created state",
        detail="Task must be awaiting_approval",
    )
    result = runner.invoke(app, ["task", "approve", "task_abc123"])
    assert result.exit_code == 1
    assert "Cannot approve" in result.output


# ---------------------------------------------------------------------------
# reject
# ---------------------------------------------------------------------------


def test_task_reject_success(runner, isolated_tasks_dir, monkeypatched_service):
    record = TaskRecord(
        task_id="task_abc123",
        project_id="proj-1",
        description="implement the feature",
        status=TaskStatus.REJECTED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        current_revision=1,
    )
    monkeypatched_service.reject_task.return_value = record

    result = runner.invoke(app, ["task", "reject", "task_abc123", "plan lacks tests"])

    assert result.exit_code == 0
    assert "rejected" in result.output.lower()
    assert "plan lacks tests" in result.output
    monkeypatched_service.reject_task.assert_called_once_with(
        "task_abc123", "plan lacks tests"
    )


def test_task_reject_missing_reason_exit_2(runner, isolated_tasks_dir):
    result = runner.invoke(app, ["task", "reject", "task_abc123"])
    assert result.exit_code == 2


def test_task_reject_empty_reason_exit_2(runner, isolated_tasks_dir, monkeypatched_service):
    result = runner.invoke(app, ["task", "reject", "task_abc123", ""])
    assert result.exit_code == 2
    monkeypatched_service.reject_task.assert_not_called()


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------


def test_task_cancel_success(runner, isolated_tasks_dir, monkeypatched_service):
    record = TaskRecord(
        task_id="task_abc123",
        project_id="proj-1",
        description="implement the feature",
        status=TaskStatus.CANCELLED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        current_revision=None,
    )
    monkeypatched_service.cancel_task.return_value = record

    result = runner.invoke(app, ["task", "cancel", "task_abc123"])

    assert result.exit_code == 0
    assert "cancelled" in result.output.lower()
    monkeypatched_service.cancel_task.assert_called_once_with("task_abc123")


def test_task_cancel_invalid_transition_exit_1(runner, isolated_tasks_dir, monkeypatched_service):
    monkeypatched_service.cancel_task.side_effect = InvalidTaskTransitionError(
        "Cannot cancel task in planning state",
        detail="Wait for planning to complete",
    )
    result = runner.invoke(app, ["task", "cancel", "task_abc123"])
    assert result.exit_code == 1
    assert "Cannot cancel" in result.output


# ---------------------------------------------------------------------------
# _task_service is monkeypatchable
# ---------------------------------------------------------------------------


def test_task_service_is_monkeypatchable(runner, isolated_tasks_dir, monkeypatch):
    """Verify _task_service can be replaced for testing."""
    called = {}

    def fake_service():
        called["invoked"] = True
        svc = MagicMock()
        svc.list_tasks.return_value = []
        return svc

    monkeypatch.setattr(task_cmd, "_task_service", fake_service)

    result = runner.invoke(app, ["task", "list"])
    assert result.exit_code == 0
    assert called.get("invoked") is True


# ---------------------------------------------------------------------------
# Unexpected FactoryLabError maps to exit 1
# ---------------------------------------------------------------------------


def test_task_create_factory_error_exit_1(runner, isolated_tasks_dir, monkeypatched_service):
    monkeypatched_service.create_task.side_effect = FactoryLabError(
        "Unexpected failure", detail="something broke"
    )
    result = runner.invoke(app, ["task", "create", "proj-1", "implement the feature"])
    assert result.exit_code == 1
    assert "Unexpected failure" in result.output
