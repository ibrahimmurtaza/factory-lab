"""Tests for the `factory project inspect` CLI command."""

from __future__ import annotations

import shutil

import pytest
from typer.testing import CliRunner

import factory.cli.main as cli_main
from factory.cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    target = tmp_path / "config.json"
    monkeypatch.setattr(cli_main, "default_config_path", lambda: target)
    return target


def _register_project(runner, project_path: str) -> str:
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["project", "add", project_path])
    assert result.exit_code == 0
    # The id is printed on the "id:" line.
    for line in result.output.splitlines():
        if line.strip().startswith("id:"):
            return line.strip().split(":", 1)[1].strip()
    raise AssertionError("no project id printed")


def test_inspect_unknown_project_id(runner, isolated_config):
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["project", "inspect", "unknown-id"])
    assert result.exit_code != 0


def test_inspect_missing_repository(runner, isolated_config, tmp_path):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    project_id = _register_project(runner, str(real_dir))
    # Remove the repository after registration so inspection finds it missing.
    shutil.rmtree(real_dir)
    result = runner.invoke(app, ["project", "inspect", project_id])
    assert result.exit_code != 0


def test_inspect_python_project(runner, isolated_config, tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["fastapi"]\n', encoding="utf-8"
    )
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# hi\n", encoding="utf-8")
    project_id = _register_project(runner, str(tmp_path))

    result = runner.invoke(app, ["project", "inspect", project_id])
    assert result.exit_code == 0
    assert tmp_path.name in result.output
    assert "Python" in result.output
    assert "FastAPI" in result.output


def test_inspect_javascript_project(runner, isolated_config, tmp_path):
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"react": "^18.0"}}', encoding="utf-8"
    )
    (tmp_path / "app.js").write_text("console.log(1);\n", encoding="utf-8")
    project_id = _register_project(runner, str(tmp_path))

    result = runner.invoke(app, ["project", "inspect", project_id])
    assert result.exit_code == 0
    assert "JavaScript" in result.output
    assert "React" in result.output


def test_inspect_infrastructure(runner, isolated_config, tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM python:3.11\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("services:\n", encoding="utf-8")
    project_id = _register_project(runner, str(tmp_path))

    result = runner.invoke(app, ["project", "inspect", project_id])
    assert result.exit_code == 0
    assert "Docker" in result.output
    assert "Docker Compose" in result.output


def test_inspect_git_metadata(runner, isolated_config, tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/develop\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    project_id = _register_project(runner, str(tmp_path))

    result = runner.invoke(app, ["project", "inspect", project_id])
    assert result.exit_code == 0
    assert "develop" in result.output


def test_inspect_does_not_modify_repo(runner, isolated_config, tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    before = (tmp_path / "main.py").read_text(encoding="utf-8")
    project_id = _register_project(runner, str(tmp_path))

    runner.invoke(app, ["project", "inspect", project_id])
    after = (tmp_path / "main.py").read_text(encoding="utf-8")
    assert before == after
