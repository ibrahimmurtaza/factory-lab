"""Tests for repository inspection."""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.intelligence.repository.inspector import (
    EXCLUDED_DIRS,
    RepositoryInspector,
)


def _write(root: Path, relative: str, content: str = "") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _mkdir(root: Path, relative: str) -> Path:
    path = root / relative
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_basic_inspection(tmp_path):
    _write(tmp_path, "README.md", "# hello")
    _write(tmp_path, "main.py", "print(1)")
    _mkdir(tmp_path, "src")
    _write(tmp_path, "src/module.py", "x = 1")
    _mkdir(tmp_path, "tests")
    _write(tmp_path, "tests/test_module.py", "def test():\n    pass\n")

    inspector = RepositoryInspector()
    context = inspector.inspect(tmp_path)

    assert context.structure.root == str(tmp_path.resolve())
    assert "README.md" in context.structure.top_level_files
    assert "main.py" in context.structure.top_level_files
    assert "src" in context.structure.top_level_dirs
    assert "tests" in context.structure.top_level_dirs
    assert "README.md" in context.structure.readme_files
    assert "src" in context.structure.source_dirs
    assert "tests" in context.structure.test_dirs


def test_missing_repository_raises(tmp_path):
    inspector = RepositoryInspector()
    with pytest.raises(FileNotFoundError):
        inspector.inspect(tmp_path / "does-not-exist")


def test_path_is_not_directory_raises(tmp_path):
    file_path = tmp_path / "afile.txt"
    file_path.write_text("x")
    inspector = RepositoryInspector()
    with pytest.raises(NotADirectoryError):
        inspector.inspect(file_path)


def test_excluded_dirs_not_traversed(tmp_path):
    _mkdir(tmp_path, "node_modules")
    _write(tmp_path, "node_modules/lib.js", "x")
    _mkdir(tmp_path, ".venv")
    _write(tmp_path, ".venv/site.py", "x")
    _mkdir(tmp_path, "dist")
    _write(tmp_path, "dist/bundle.js", "x")
    _mkdir(tmp_path, "__pycache__")
    _write(tmp_path, "__pycache__/main.cpython-311.pyc", "x")
    _write(tmp_path, "real_source.py", "x = 1")

    inspector = RepositoryInspector()
    context = inspector.inspect(tmp_path)

    for excluded in EXCLUDED_DIRS:
        assert excluded not in context.structure.top_level_dirs
    assert "real_source.py" in context.structure.top_level_files


def test_readme_and_git_detection(tmp_path):
    _write(tmp_path, "README.md", "# hello")
    _mkdir(tmp_path, ".git")
    _write(tmp_path, ".git/HEAD", "ref: refs/heads/main")

    inspector = RepositoryInspector()
    context = inspector.inspect(tmp_path)

    assert context.structure.git_present is True
    assert "README.md" in context.structure.readme_files

    git_meta = inspector.git_metadata(tmp_path)
    assert git_meta is not None
    assert git_meta.branch == "main"


def test_git_metadata_detached_head(tmp_path):
    _mkdir(tmp_path, ".git")
    _write(
        tmp_path,
        ".git/HEAD",
        "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
    )

    inspector = RepositoryInspector()
    git_meta = inspector.git_metadata(tmp_path)
    assert git_meta is not None
    assert git_meta.commit == "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
    assert git_meta.branch is None


def test_no_git_metadata_when_absent(tmp_path):
    _write(tmp_path, "main.py", "x = 1")
    inspector = RepositoryInspector()
    assert inspector.git_metadata(tmp_path) is None


def test_symlink_outside_root_not_followed(tmp_path):
    outside = tmp_path.parent / "outside_secret.txt"
    outside.write_text("secret")
    link = tmp_path / "link.outside"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks not supported in this environment")

    inspector = RepositoryInspector()
    context = inspector.inspect(tmp_path)
    assert "link.outside" in context.structure.top_level_files


def test_repository_not_modified(tmp_path):
    _write(tmp_path, "main.py", "print(1)")
    _write(tmp_path, "README.md", "# hi")

    before = {
        p: (tmp_path / p).read_text(encoding="utf-8")
        for p in ["main.py", "README.md"]
    }

    inspector = RepositoryInspector()
    inspector.inspect(tmp_path)
    inspector.git_metadata(tmp_path)

    after = {
        p: (tmp_path / p).read_text(encoding="utf-8")
        for p in ["main.py", "README.md"]
    }
    assert before == after


def test_unreadable_manifest_handled_gracefully(tmp_path):
    _write(tmp_path, "package.json", '{"name": "x"}')
    inspector = RepositoryInspector()
    context = inspector.inspect(tmp_path)
    assert context.structure.git_present is False


def test_doc_dir_detection(tmp_path):
    _mkdir(tmp_path, "docs")
    _write(tmp_path, "docs/guide.md", "# guide")
    _mkdir(tmp_path, "documentation")
    _write(tmp_path, "documentation/api.md", "# api")

    inspector = RepositoryInspector()
    context = inspector.inspect(tmp_path)

    assert "docs" in context.structure.doc_dirs
    assert "documentation" in context.structure.doc_dirs
