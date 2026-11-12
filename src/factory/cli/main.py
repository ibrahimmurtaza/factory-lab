"""Command-line interface entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from factory.config.manager import default_config_path, JsonConfigStorage, ConfigManager
from factory.control.projects.service import ProjectService
from factory.errors import FactoryLabError, ProjectNotFoundError
from factory.intelligence.detection.base import DetectorRegistry
from factory.intelligence.detection.frameworks import FrameworkDetector
from factory.intelligence.detection.infrastructure import InfrastructureDetector
from factory.intelligence.detection.languages import LanguageDetector
from factory.intelligence.engine import ProjectProfiler
from factory.intelligence.repository.inspector import RepositoryInspector

app = typer.Typer(
    name="factory",
    help="Factory Lab - Autonomous AI-powered software engineering factory.",
)

_project_app = typer.Typer(
    name="project",
    help="Manage registered projects.",
)
app.add_typer(_project_app, name="project")


def _config_manager() -> ConfigManager:
    return ConfigManager(JsonConfigStorage(default_config_path()))


@app.command()
def init() -> None:
    """Initialize the local Factory Lab configuration directory."""
    manager = _config_manager()
    config_path = default_config_path()
    already_exists = config_path.exists()

    try:
        manager.initialize(config_path)
    except FactoryLabError as exc:
        typer.secho(f"Error: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if already_exists:
        typer.secho(
            f"Factory Lab already initialized. Configuration: {config_path}",
            fg=typer.colors.YELLOW,
        )
    else:
        typer.secho(
            f"Factory Lab initialized. Configuration: {config_path}",
            fg=typer.colors.GREEN,
        )


@_project_app.command("add")
def project_add(path: str) -> None:
    """Register a local software project.

    Args:
        path: Filesystem path to the project directory.
    """
    manager = _config_manager()
    service = ProjectService(manager)

    try:
        project = service.add_project(path)
    except FactoryLabError as exc:
        typer.secho(f"Error: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho(f"Project registered: {project.name}", fg=typer.colors.GREEN)
    typer.echo(f"  id:    {project.id}")
    typer.echo(f"  path:  {project.path}")


@_project_app.command("list")
def project_list() -> None:
    """List all registered projects."""
    manager = _config_manager()
    service = ProjectService(manager)

    try:
        projects = service.list_projects()
    except FactoryLabError as exc:
        typer.secho(f"Error: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if not projects:
        typer.secho("No projects registered.", fg=typer.colors.YELLOW)
        typer.echo("Use 'factory project add <path>' to register a project.")
        return

    typer.echo(f"{'ID':<38} {'NAME':<24} PATH")
    typer.echo("-" * 78)
    for project in projects:
        typer.echo(f"{project.id:<38} {project.name:<24} {project.path}")


def _profiler() -> ProjectProfiler:
    manager = _config_manager()
    inspector = RepositoryInspector()
    registry = DetectorRegistry(
        detectors=[
            LanguageDetector(),
            FrameworkDetector(),
            InfrastructureDetector(),
        ]
    )
    return ProjectProfiler(
        config_manager=manager,
        inspector=inspector,
        registry=registry,
    )


@_project_app.command("inspect")
def project_inspect(project_id: str) -> None:
    """Inspect a registered project and report its technology stack.

    Args:
        project_id: Stable identifier of a registered project.
    """
    profiler = _profiler()

    try:
        profile = profiler.profile(project_id)
    except ProjectNotFoundError as exc:
        typer.secho(f"Error: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    except (FileNotFoundError, NotADirectoryError) as exc:
        typer.secho(f"Error: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    except FactoryLabError as exc:
        typer.secho(f"Error: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    _display_profile(profile)


def _display_profile(profile) -> None:
    typer.secho(f"Project: {profile.project_name}", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  id:        {profile.project_id}")
    typer.echo(f"  repository: {profile.repository_root}")
    typer.echo(f"  inspected:  {profile.inspected_at}")

    typer.secho("\nLanguages:", fg=typer.colors.CYAN, bold=True)
    if profile.languages:
        for detection in profile.languages:
            typer.echo(f"  - {detection.name}")
            for evidence in detection.evidence:
                typer.echo(f"      * {evidence}")
    else:
        typer.echo("  (none detected)")

    typer.secho("\nFrameworks:", fg=typer.colors.CYAN, bold=True)
    if profile.frameworks:
        for detection in profile.frameworks:
            typer.echo(f"  - {detection.name}")
            for evidence in detection.evidence:
                typer.echo(f"      * {evidence}")
    else:
        typer.echo("  (none detected)")

    typer.secho("\nInfrastructure & tooling:", fg=typer.colors.CYAN, bold=True)
    if profile.infrastructure:
        for detection in profile.infrastructure:
            typer.echo(f"  - {detection.name}")
            for evidence in detection.evidence:
                typer.echo(f"      * {evidence}")
    else:
        typer.echo("  (none detected)")

    typer.secho("\nRepository structure:", fg=typer.colors.CYAN, bold=True)
    structure = profile.structure
    typer.echo(f"  top-level files:   {', '.join(structure.top_level_files) or '(none)'}")
    typer.echo(f"  top-level dirs:    {', '.join(structure.top_level_dirs) or '(none)'}")
    if structure.readme_files:
        typer.echo(f"  readme files:      {', '.join(structure.readme_files)}")
    if structure.git_present:
        typer.echo("  git repository:    yes")

    if profile.git_metadata:
        typer.secho("\nGit metadata:", fg=typer.colors.CYAN, bold=True)
        if profile.git_metadata.branch:
            typer.echo(f"  branch:  {profile.git_metadata.branch}")
        if profile.git_metadata.commit:
            typer.echo(f"  commit:  {profile.git_metadata.commit}")

    typer.echo(f"\nTotal detections: {profile.detection_count()}")


def main() -> None:  # pragma: no cover - entry point
    app()


if __name__ == "__main__":  # pragma: no cover - entry point
    main()
