"""Language detectors based on file extensions and manifest files."""

from __future__ import annotations

from pathlib import Path
from typing import List

from factory.intelligence.detection.base import (
    Detector,
    Detection,
    DetectionContext,
    parse_json,
    parse_toml,
)

# Mapping of file extensions to language names.
EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".cs": "C#",
    ".vb": "Visual Basic",
    ".go": "Go",
    ".rs": "Rust",
    ".php": "PHP",
    ".rb": "Ruby",
    ".swift": "Swift",
    ".dart": "Dart",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hxx": "C++",
}

# Manifest filenames that imply a language.
MANIFEST_LANGUAGE_MAP: dict[str, str] = {
    "pyproject.toml": "Python",
    "requirements.txt": "Python",
    "requirements.in": "Python",
    "setup.py": "Python",
    "setup.cfg": "Python",
    "package.json": "JavaScript",
    "tsconfig.json": "TypeScript",
    "go.mod": "Go",
    "Cargo.toml": "Rust",
    "pom.xml": "Java",
    "build.gradle": "Java",
    "build.gradle.kts": "Kotlin",
    "*.csproj": "C#",
    "*.sln": "C#",
    "composer.json": "PHP",
    "Gemfile": "Ruby",
    "pubspec.yaml": "Dart",
    "Package.swift": "Swift",
}

# Glob patterns for C# project/solution files (handled specially below).
CSHARP_GLOBS = ("*.csproj", "*.sln")


class LanguageDetector(Detector):
    """Detects programming languages from file extensions and manifests."""

    @property
    def category(self) -> str:
        return "language"

    def detect(self, context: DetectionContext) -> List[Detection]:
        detected: dict[str, List[str]] = {}

        # Evidence from file extensions present in the repository.
        for file_path in context.files:
            suffix = Path(file_path).suffix.lower()
            language = EXTENSION_LANGUAGE_MAP.get(suffix)
            if language:
                detected.setdefault(language, []).append(f"file: {file_path}")

        # Evidence from manifest filenames.
        for manifest in context.files:
            name = Path(manifest).name.lower()
            language = MANIFEST_LANGUAGE_MAP.get(name)
            if language:
                detected.setdefault(language, []).append(f"manifest: {manifest}")
            # Handle C# glob patterns separately.
            for pattern in CSHARP_GLOBS:
                if self._matches_glob(name, pattern):
                    detected.setdefault("C#", []).append(f"manifest: {manifest}")
                    break

        # Evidence from parsed manifest contents.
        self._evidence_from_pyproject(context, detected)
        self._evidence_from_package_json(context, detected)
        self._evidence_from_go_mod(context, detected)
        self._evidence_from_cargo_toml(context, detected)
        self._evidence_from_pom_xml(context, detected)
        self._evidence_from_composer_json(context, detected)
        self._evidence_from_gemfile(context, detected)
        self._evidence_from_pubspec(context, detected)

        detections: List[Detection] = []
        for language, evidence in sorted(detected.items()):
            detections.append(
                Detection(name=language, category="language", evidence=evidence)
            )
        return detections

    @staticmethod
    def _matches_glob(name: str, pattern: str) -> bool:
        import fnmatch

        return fnmatch.fnmatch(name.lower(), pattern.lower())

    @staticmethod
    def _evidence_from_pyproject(
        context: DetectionContext, detected: dict[str, List[str]]
    ) -> None:
        for path in context.all_detection_files():
            if Path(path).name.lower() != "pyproject.toml":
                continue
            data = parse_toml(Path(path))
            if not data:
                continue
            project = data.get("project", {})
            if project:
                detected.setdefault("Python", []).append(
                    f"pyproject.toml defines project metadata"
                )
            build_system = data.get("build-system", {})
            if build_system:
                requires = build_system.get("requires", [])
                if requires:
                    detected.setdefault("Python", []).append(
                        f"pyproject.toml build-system requires: {', '.join(requires)}"
                    )

    @staticmethod
    def _evidence_from_package_json(
        context: DetectionContext, detected: dict[str, List[str]]
    ) -> None:
        for path in context.all_detection_files():
            if Path(path).name.lower() != "package.json":
                continue
            data = parse_json(Path(path))
            if isinstance(data, dict):
                detected.setdefault("JavaScript", []).append(
                    "package.json present"
                )
                # TypeScript is indicated by devDependency on typescript or tsconfig.
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                if "typescript" in deps:
                    detected.setdefault("TypeScript", []).append(
                        "package.json depends on typescript"
                    )

    @staticmethod
    def _evidence_from_go_mod(
        context: DetectionContext, detected: dict[str, List[str]]
    ) -> None:
        for path in context.all_detection_files():
            if Path(path).name.lower() == "go.mod":
                detected.setdefault("Go", []).append(f"manifest: {path}")

    @staticmethod
    def _evidence_from_cargo_toml(
        context: DetectionContext, detected: dict[str, List[str]]
    ) -> None:
        for path in context.all_detection_files():
            if Path(path).name.lower() == "cargo.toml":
                detected.setdefault("Rust", []).append(f"manifest: {path}")

    @staticmethod
    def _evidence_from_pom_xml(
        context: DetectionContext, detected: dict[str, List[str]]
    ) -> None:
        for path in context.all_detection_files():
            if Path(path).name.lower() == "pom.xml":
                detected.setdefault("Java", []).append(f"manifest: {path}")

    @staticmethod
    def _evidence_from_composer_json(
        context: DetectionContext, detected: dict[str, List[str]]
    ) -> None:
        for path in context.all_detection_files():
            if Path(path).name.lower() == "composer.json":
                detected.setdefault("PHP", []).append(f"manifest: {path}")

    @staticmethod
    def _evidence_from_gemfile(
        context: DetectionContext, detected: dict[str, List[str]]
    ) -> None:
        for path in context.all_detection_files():
            if Path(path).name.lower() == "gemfile":
                detected.setdefault("Ruby", []).append(f"manifest: {path}")

    @staticmethod
    def _evidence_from_pubspec(
        context: DetectionContext, detected: dict[str, List[str]]
    ) -> None:
        for path in context.all_detection_files():
            if Path(path).name.lower() == "pubspec.yaml":
                detected.setdefault("Dart", []).append(f"manifest: {path}")
