"""Tests for the CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import factory.cli.main as cli_main
from factory.cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Point the CLI config at a temporary path and yield it."""
    target = tmp_path / "config.json"
    monkeypatch.setattr(cli_main, "default_config_path", lambda: target)
    return target


def test_init_first_time(runner, isolated_config):
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert isolated_config.exists()
    assert "initialized" in result.output.lower()


def test_init_repeated(runner, isolated_config):
    result1 = runner.invoke(app, ["init"])
    assert result1.exit_code == 0
    result2 = runner.invoke(app, ["init"])
    assert result2.exit_code == 0


def test_project_add_valid(runner, isolated_config, tmp_path):
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["project", "add", str(tmp_path)])
    assert result.exit_code == 0
    assert tmp_path.name in result.output
    assert str(tmp_path.resolve()) in result.output


def test_project_add_invalid_path(runner, isolated_config):
    result = runner.invoke(app, ["project", "add", "/nonexistent/path/xyz"])
    assert result.exit_code != 0


def test_project_add_duplicate(runner, isolated_config, tmp_path):
    runner.invoke(app, ["init"])
    runner.invoke(app, ["project", "add", str(tmp_path)])
    result = runner.invoke(app, ["project", "add", str(tmp_path)])
    assert result.exit_code != 0


def test_project_list_empty(runner, isolated_config):
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["project", "list"])
    assert result.exit_code == 0
    assert "No projects registered" in result.output


def test_project_list_multiple(runner, isolated_config, tmp_path):
    runner.invoke(app, ["init"])
    runner.invoke(app, ["project", "add", str(tmp_path)])
    sub = tmp_path / "sub"
    sub.mkdir()
    runner.invoke(app, ["project", "add", str(sub)])
    result = runner.invoke(app, ["project", "list"])
    assert result.exit_code == 0
    assert tmp_path.name in result.output
    assert sub.name in result.output
