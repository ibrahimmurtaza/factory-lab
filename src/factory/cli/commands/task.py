"""CLI task commands (M4-08).

Implements eight Typer commands under ``factory task``:
create, list, status, show, plan, approve, reject, cancel.

All commands delegate business logic to :class:`TaskService`; this module
contains only input validation, output formatting, and user-facing error
handling. A new :class:`TaskService` is constructed per command execution
(via :func:`_task_service`); there is no module-level singleton.
"""

from __future__ import annotations

from typing import Optional

import typer

from factory.cli.main import app
from factory.config.manager import default_config_path, JsonConfigStorage, ConfigManager
from factory.control.actor import ActorResolver
from factory.control.planner import DeterministicTaskPlanner
from factory.control.projects.service import ProjectService
from factory.control.task import TaskService
from factory.control.task_storage import (
    JsonTaskStorage,
    default_tasks_dir,
)
from factory.errors import FactoryLabError
from factory.intelligence.detection.base import DetectorRegistry
from factory.intelligence.detection.frameworks import FrameworkDetector
from factory.intelligence.detection.infrastructure import InfrastructureDetector
from factory.intelligence.detection.languages import LanguageDetector
from factory.intelligence.engine import ProjectProfiler
from factory.intelligence.repository.inspector import RepositoryInspector

task_app = typer.Typer(
    name="task",
    help="Manage tasks: create, plan, approve, reject, cancel.",
)


def _config_manager() -> ConfigManager:
    return ConfigManager(JsonConfigStorage(default_config_path()))


def _task_service() -> TaskService:
    """Assemble and return a :class:`TaskService` for command execution.

    Constructs all required dependencies (storage, project service, profiler,
    planner, actor resolver) and injects them into a new :class:`TaskService`.
    Called once per command; no module-level singleton.

    This function is monkeypatchable for testing.
    """
    config_manager = _config_manager()
    storage = JsonTaskStorage(default_tasks_dir())
    project_service = ProjectService(config_manager)

    inspector = RepositoryInspector()
    registry = DetectorRegistry(
        detectors=[
            LanguageDetector(),
            FrameworkDetector(),
            InfrastructureDetector(),
        ]
    )
    profiler = ProjectProfiler(
        config_manager=config_manager,
        inspector=inspector,
        registry=registry,
    )

    planner = DeterministicTaskPlanner()
    actor_resolver = ActorResolver()

    return TaskService(
        storage=storage,
        project_service=project_service,
        profiler=profiler,
        planner=planner,
        actor_resolver=actor_resolver,
    )


def _handle_error(exc: FactoryLabError) -> None:
    """Print an expected application error to stderr and exit with code 1."""
    typer.secho(f"Error: {exc}", err=True, fg=typer.colors.RED)
    raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@task_app.command("create")
def task_create(
    project_id: str = typer.Argument(..., help="Registered project identifier."),
    description: str = typer.Argument(..., help="Task description."),
) -> None:
    """Register a new task in ``created`` state."""
    if not project_id or not project_id.strip():
        typer.secho(
            "Error: Project ID must not be empty", err=True, fg=typer.colors.RED
        )
        raise typer.Exit(code=2)
    if not description or not description.strip():
        typer.secho(
            "Error: Task description must not be empty",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    service = _task_service()
    try:
        record = service.create_task(project_id.strip(), description.strip())
    except FactoryLabError as exc:
        _handle_error(exc)

    typer.secho(f"Task created: {record.task_id}", fg=typer.colors.GREEN)
    typer.echo(f"  status:    {record.status.value}")
    typer.echo(f"  project:   {record.project_id}")
    typer.echo(f"  description: {record.description}")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@task_app.command("list")
def task_list() -> None:
    """List all registered task records."""
    service = _task_service()
    try:
        records = service.list_tasks()
    except FactoryLabError as exc:
        _handle_error(exc)

    if not records:
        typer.secho("No tasks registered.", fg=typer.colors.YELLOW)
        typer.echo("Use 'factory task create <project-id> \"<desc>\"' to create one.")
        return

    typer.echo(f"{'TASK ID':<38} {'STATUS':<20} PROJECT")
    typer.echo("-" * 70)
    for record in records:
        typer.echo(
            f"{record.task_id:<38} {record.status.value:<20} {record.project_id}"
        )


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@task_app.command("status")
def task_status(
    task_id: str = typer.Argument(..., help="Task identifier."),
) -> None:
    """Print a concise task overview."""
    service = _task_service()
    try:
        record = service.get_task(task_id)
    except FactoryLabError as exc:
        _handle_error(exc)

    revision = record.current_revision
    revision_status = "none"
    if revision is not None:
        for rev in record.plan_revisions:
            if rev.revision_number == revision:
                revision_status = rev.status
                break

    typer.echo(f"Task: {record.task_id}")
    typer.echo(f"  status:       {record.status.value}")
    typer.echo(f"  project:      {record.project_id}")
    typer.echo(f"  current_rev:  {revision if revision is not None else '-'}")
    typer.echo(f"  rev_status:   {revision_status}")


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


@task_app.command("show")
def task_show(
    task_id: str = typer.Argument(..., help="Task identifier."),
) -> None:
    """Print the complete task record."""
    service = _task_service()
    try:
        record = service.get_task(task_id)
    except FactoryLabError as exc:
        _handle_error(exc)

    typer.echo(f"Task ID:      {record.task_id}")
    typer.echo(f"Project ID:   {record.project_id}")
    typer.echo(f"Description:  {record.description}")
    typer.echo(f"Status:       {record.status.value}")
    typer.echo(f"Created:      {record.created_at.isoformat()}")
    typer.echo(f"Updated:      {record.updated_at.isoformat()}")
    typer.echo(f"Current Rev:  {record.current_revision if record.current_revision is not None else 'none'}")

    typer.echo("\nPlan Revisions:")
    if not record.plan_revisions:
        typer.echo("  (none)")
    for rev in record.plan_revisions:
        typer.echo(f"  Rev {rev.revision_number}: {rev.status}")
        typer.echo(f"    created: {rev.created_at.isoformat()}")
        if rev.approval is not None:
            typer.echo(
                f"    approval: {rev.approval.decision} by {rev.approval.actor}"
            )
            if rev.approval.reason:
                typer.echo(f"    reason:   {rev.approval.reason}")
        typer.echo(f"    summary:  {rev.plan.summary}")

    typer.echo("\nLifecycle History:")
    if not record.lifecycle_history:
        typer.echo("  (none)")
    for event in record.lifecycle_history:
        from_status = (
            event.from_status.value if event.from_status is not None else "none"
        )
        typer.echo(
            f"  {from_status} -> {event.to_status.value} at {event.timestamp.isoformat()}"
        )
        if event.actor:
            typer.echo(f"    actor: {event.actor}")
        if event.reason:
            typer.echo(f"    reason: {event.reason}")


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


@task_app.command("plan")
def task_plan(
    task_id: str = typer.Argument(..., help="Task identifier."),
) -> None:
    """Generate an implementation plan and transition to ``awaiting_approval``."""
    service = _task_service()
    try:
        record = service.plan_task(task_id)
    except FactoryLabError as exc:
        _handle_error(exc)

    typer.secho(
        f"Plan created for task {record.task_id}; revision {record.current_revision}",
        fg=typer.colors.GREEN,
    )
    typer.echo(f"  status: {record.status.value}")


# ---------------------------------------------------------------------------
# approve
# ---------------------------------------------------------------------------


@task_app.command("approve")
def task_approve(
    task_id: str = typer.Argument(..., help="Task identifier."),
) -> None:
    """Approve the current plan revision and transition to ``approved``."""
    service = _task_service()
    try:
        record = service.approve_task(task_id)
    except FactoryLabError as exc:
        _handle_error(exc)

    typer.secho(f"Task {record.task_id} approved.", fg=typer.colors.GREEN)
    typer.echo(f"  status: {record.status.value}")


# ---------------------------------------------------------------------------
# reject
# ---------------------------------------------------------------------------


@task_app.command("reject")
def task_reject(
    task_id: str = typer.Argument(..., help="Task identifier."),
    reason: str = typer.Argument(..., help="Reason for rejection."),
) -> None:
    """Reject the current plan revision and transition to ``rejected``."""
    if not reason or not reason.strip():
        typer.secho(
            "Error: Rejection reason must not be empty",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    service = _task_service()
    try:
        record = service.reject_task(task_id, reason.strip())
    except FactoryLabError as exc:
        _handle_error(exc)

    typer.secho(f"Task {record.task_id} rejected.", fg=typer.colors.YELLOW)
    typer.echo(f"  status: {record.status.value}")
    typer.echo(f"  reason: {reason.strip()}")


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------


@task_app.command("cancel")
def task_cancel(
    task_id: str = typer.Argument(..., help="Task identifier."),
) -> None:
    """Cancel the task when the current lifecycle state permits."""
    service = _task_service()
    try:
        record = service.cancel_task(task_id)
    except FactoryLabError as exc:
        _handle_error(exc)

    typer.secho(f"Task {record.task_id} cancelled.", fg=typer.colors.YELLOW)
    typer.echo(f"  status: {record.status.value}")
