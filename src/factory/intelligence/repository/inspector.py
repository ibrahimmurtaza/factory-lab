"""Read-only repository inspection.

The inspector observes a repository's layout and contents without modifying
it, without executing any code from it, and without following symlinks that
escape the repository root.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from factory.intelligence.repository.models import (
    GitMetadata,
    RepositoryStructure,
)

__all__ = [
    "EXCLUDED_DIRS",
    "RepositoryInspector",
    "InspectionContext",
]


# Directories that are generated, large, or not part of project source.
# These are excluded from traversal and never read.
EXCLUDED_DIRS: Set[str] = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "target",
    "vendor",
}

# Common README filenames (matched case-insensitively).
README_NAMES: Set[str] = {
    "readme.md",
    "readme.rst",
    "readme.txt",
    "readme",
}

# Common documentation directory names.
DOC_DIR_NAMES: Set[str] = {"docs", "documentation"}

# Common source directory names.
SOURCE_DIR_NAMES: Set[str] = {"src", "source", "lib", "app", "packages"}

# Common test directory names.
TEST_DIR_NAMES: Set[str] = {"test", "tests", "__tests__", "spec", "specs"}

# Dependency manifest filenames (root or shallow).
DEPENDENCY_MANIFEST_NAMES: Set[str] = {
    "pyproject.toml",
    "requirements.txt",
    "requirements.in",
    "setup.py",
    "setup.cfg",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "tsconfig.json",
    "go.mod",
    "go.sum",
    "Cargo.toml",
    "Cargo.lock",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "*.csproj",
    "*.sln",
    "composer.json",
    "composer.lock",
    "Gemfile",
    "Gemfile.lock",
    "pubspec.yaml",
    "pubspec.lock",
    "Package.swift",
}

# Configuration filenames (root or shallow).
CONFIG_FILE_NAMES: Set[str] = {
    ".gitignore",
    ".dockerignore",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "jest.config.js",
    "jest.config.ts",
    "webpack.config.js",
    "babel.config.js",
    "eslintrc.json",
    "eslintrc.js",
    "prettier.config.js",
    "mkdocs.yml",
    "conf.py",
}

# Manifests whose contents are useful for technology detection.
DETECTION_MANIFEST_NAMES: Set[str] = {
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "composer.json",
    "Gemfile",
    "pubspec.yaml",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
}

MAX_FILE_READ_BYTES = 1_048_576  # 1 MiB
MAX_WALK_ENTRIES = 20_000


@dataclass
class InspectionContext:
    """Collected raw facts used by both the inspector and detectors."""

    root: Path
    structure: RepositoryStructure
    manifest_contents: Dict[str, str]
    all_files: List[str]


class RepositoryInspector:
    """Inspects a repository directory in a safe, read-only manner."""

    def __init__(
        self,
        excluded_dirs: Optional[Set[str]] = None,
        max_entries: int = MAX_WALK_ENTRIES,
    ) -> None:
        self._excluded_dirs = set(excluded_dirs) if excluded_dirs else set(EXCLUDED_DIRS)
        self._max_entries = max_entries

    def inspect(self, root: str | Path) -> InspectionContext:
        """Inspect ``root`` and return an :class:`InspectionContext`.

        Args:
            root: Path to the repository root.

        Raises:
            FileNotFoundError: If ``root`` does not exist.
            NotADirectoryError: If ``root`` is not a directory.
        """
        root_path = Path(root).expanduser().resolve(strict=False)

        if not root_path.exists():
            raise FileNotFoundError(f"Repository directory does not exist: {root}")
        if not root_path.is_dir():
            raise NotADirectoryError(f"Repository path is not a directory: {root}")

        top_level_files: List[str] = []
        top_level_dirs: List[str] = []
        readme_files: List[str] = []
        doc_dirs: List[str] = []
        source_dirs: List[str] = []
        test_dirs: List[str] = []
        config_files: List[str] = []
        dependency_manifests: List[str] = []
        all_files: List[str] = []
        manifest_contents: Dict[str, str] = {}
        git_present = False

        entry_count = 0
        for entry in self._safe_children(root_path):
            entry_count += 1
            if entry_count > self._max_entries:
                break

            try:
                relative = entry.relative_to(root_path)
            except ValueError:
                continue

            relative_str = str(relative)
            name = entry.name
            name_lower = name.lower()

            if entry.is_symlink():
                # Resolve and reject symlinks that escape the repository root.
                try:
                    resolved = entry.resolve(strict=False)
                except OSError:
                    continue
                try:
                    resolved.relative_to(root_path)
                except ValueError:
                    continue  # symlink escapes root; ignore

            if entry.is_dir():
                if name == ".git":
                    git_present = True
                    continue  # detect git, but never traverse into it
                if name_lower in self._excluded_dirs:
                    continue
                top_level_dirs.append(name)

                if name_lower in DOC_DIR_NAMES:
                    doc_dirs.append(relative_str)
                elif name_lower in SOURCE_DIR_NAMES:
                    source_dirs.append(relative_str)
                elif name_lower in TEST_DIR_NAMES:
                    test_dirs.append(relative_str)

                if name == ".git":
                    git_present = True

                # Shallow recurse into immediate child directories for
                # manifests and config files only.
                for child in self._safe_children(entry):
                    try:
                        child_relative = child.relative_to(root_path)
                    except ValueError:
                        continue
                    child_str = str(child_relative)
                    child_name_lower = child.name.lower()
                    if child.is_dir():
                        continue
                    if child_name_lower in DEPENDENCY_MANIFEST_NAMES:
                        dependency_manifests.append(child_str)
                        self._read_manifest(child, manifest_contents, child_str)
                        all_files.append(child_str)
                    elif child_name_lower in CONFIG_FILE_NAMES:
                        config_files.append(child_str)
                        self._read_manifest(child, manifest_contents, child_str)
                    continue

            # Top-level file.
            if name_lower in README_NAMES:
                readme_files.append(relative_str)
            if name_lower in DEPENDENCY_MANIFEST_NAMES:
                dependency_manifests.append(relative_str)
                self._read_manifest(entry, manifest_contents, relative_str)
            elif name_lower in CONFIG_FILE_NAMES:
                config_files.append(relative_str)
                self._read_manifest(entry, manifest_contents, relative_str)

            top_level_files.append(name)
            all_files.append(relative_str)

        structure = RepositoryStructure(
            root=str(root_path),
            top_level_files=sorted(top_level_files),
            top_level_dirs=sorted(top_level_dirs),
            readme_files=sorted(readme_files),
            doc_dirs=sorted(doc_dirs),
            source_dirs=sorted(source_dirs),
            test_dirs=sorted(test_dirs),
            config_files=sorted(config_files),
            dependency_manifests=sorted(dependency_manifests),
            git_present=git_present,
        )

        return InspectionContext(
            root=root_path,
            structure=structure,
            manifest_contents=manifest_contents,
            all_files=all_files,
        )

    def git_metadata(self, root: str | Path) -> Optional[GitMetadata]:
        """Read Git metadata from repository files without invoking Git.

        Returns ``None`` when no Git metadata is available.
        """
        root_path = Path(root).expanduser().resolve(strict=False)
        head_file = root_path / ".git" / "HEAD"
        if not head_file.exists() or not head_file.is_file():
            return None

        branch: Optional[str] = None
        commit: Optional[str] = None
        try:
            head_text = head_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None

        if head_text.startswith("ref:"):
            ref = head_text[len("ref:"):].strip()
            if ref.startswith("refs/heads/"):
                branch = ref[len("refs/heads/"):]
        elif head_text and len(head_text) >= 7:
            # Detached HEAD pointing at a commit hash.
            commit = head_text[:40]

        return GitMetadata(branch=branch, commit=commit, is_dirty=None)

    def _safe_children(self, directory: Path):
        """Yield immediate children of ``directory`` that are safe to inspect.

        Symlinks are resolved; children whose resolved target escapes
        ``directory`` are skipped. Unreadable directories are skipped.
        """
        try:
            entries = list(directory.iterdir())
        except OSError:
            return

        for entry in entries:
            if entry.is_symlink():
                try:
                    resolved = entry.resolve(strict=False)
                except OSError:
                    continue
                try:
                    resolved.relative_to(directory)
                except ValueError:
                    continue
            yield entry

    @staticmethod
    def _read_manifest(path: Path, contents: Dict[str, str], key: str) -> None:
        """Read a manifest file's text, respecting size and error limits.

        The manifest is stored under ``key`` (a relative path) so detection
        can look it up consistently with the file inventory.
        """
        try:
            if path.stat().st_size > MAX_FILE_READ_BYTES:
                return
            contents[key] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            # Unreadable manifest; skip gracefully.
            pass
