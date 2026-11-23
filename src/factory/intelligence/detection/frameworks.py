"""Framework and runtime detectors based on manifest dependencies."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from factory.intelligence.detection.base import (
    Detector,
    Detection,
    DetectionContext,
    parse_json_text,
    parse_toml_text,
)


class FrameworkDetector(Detector):
    """Detects frameworks and runtimes from dependency declarations."""

    @property
    def category(self) -> str:
        return "framework"

    def detect(self, context: DetectionContext) -> List[Detection]:
        detections: List[Detection] = []

        # JavaScript/TypeScript frameworks from package.json.
        detections.extend(self._detect_js_frameworks(context))
        # Python frameworks from pyproject.toml / requirements.txt.
        detections.extend(self._detect_python_frameworks(context))
        # PHP frameworks from composer.json.
        detections.extend(self._detect_php_frameworks(context))
        # Ruby frameworks from Gemfile.
        detections.extend(self._detect_ruby_frameworks(context))
        # Dart/Flutter from pubspec.yaml.
        detections.extend(self._detect_dart_frameworks(context))
        # Java frameworks from build.gradle / pom.xml.
        detections.extend(self._detect_java_frameworks(context))
        # C# ASP.NET Core from csproj.
        detections.extend(self._detect_csharp_frameworks(context))

        return detections

    # ------------------------------------------------------------------
    # JavaScript / TypeScript
    # ------------------------------------------------------------------
    def _detect_js_frameworks(self, context: DetectionContext) -> List[Detection]:
        detections: List[Detection] = []

        package_json_path = None
        for file_path in context.files:
            if Path(file_path).name.lower() == "package.json":
                package_json_path = file_path
                break
        if package_json_path is None:
            return detections
        text = context.contents.get(package_json_path, "")
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return detections
        if not isinstance(data, dict):
            return detections
        deps = {
            **data.get("dependencies", {}),
            **data.get("devDependencies", {}),
        }
        dep_names = {name.lower() for name in deps}

        framework_map = {
            "react": ("React", "package.json depends on react"),
            "next": ("Next.js", "package.json depends on next"),
            "vue": ("Vue", "package.json depends on vue"),
            "@angular/core": ("Angular", "package.json depends on @angular/core"),
            "svelte": ("Svelte", "package.json depends on svelte"),
            "express": ("Express", "package.json depends on express"),
            "@nestjs/core": ("NestJS", "package.json depends on @nestjs/core"),
        }
        for dep_name, (framework, evidence) in framework_map.items():
            if dep_name in dep_names:
                detections.append(
                    Detection(name=framework, category="framework", evidence=[evidence])
                )
        return detections

    # ------------------------------------------------------------------
    # Python
    # ------------------------------------------------------------------
    def _detect_python_frameworks(self, context: DetectionContext) -> List[Detection]:
        detections: List[Detection] = []

        for path in context.all_detection_files():
            name = Path(path).name.lower()
            if name == "pyproject.toml":
                text = context.contents.get(path, "")
                data = parse_toml_text(text)
                if not isinstance(data, dict):
                    continue
                project = data.get("project", {})
                deps = list(project.get("dependencies", []))
                for optional in project.get("optional-dependencies", {}).values():
                    deps.extend(optional)
                dep_text = " ".join(deps).lower()
                if project:
                    detections.extend(self._match_python(dep_text, path))
            elif name in ("requirements.txt", "requirements.in"):
                text = context.contents.get(path, "").lower()
                detections.extend(self._match_python(text, path))

        # Deduplicate by framework name, merging evidence.
        merged: dict[str, List[str]] = {}
        for detection in detections:
            merged.setdefault(detection.name, []).extend(detection.evidence)
        return [
            Detection(name=name, category="framework", evidence=evidence)
            for name, evidence in merged.items()
        ]

    @staticmethod
    def _match_python(text: str, path: str) -> List[Detection]:
        detections: List[Detection] = []
        framework_map = {
            "fastapi": ("FastAPI", f"pyproject/requirements declares fastapi"),
            "django": ("Django", f"pyproject/requirements declares django"),
            "flask": ("Flask", f"pyproject/requirements declares flask"),
        }
        for key, (framework, evidence_template) in framework_map.items():
            if key in text:
                detections.append(
                    Detection(
                        name=framework,
                        category="framework",
                        evidence=[evidence_template],
                    )
                )
        return detections

    # ------------------------------------------------------------------
    # PHP
    # ------------------------------------------------------------------
    def _detect_php_frameworks(self, context: DetectionContext) -> List[Detection]:
        detections: List[Detection] = []
        for path in context.all_detection_files():
            if Path(path).name.lower() != "composer.json":
                continue
            text = context.contents.get(path, "")
            data = parse_json_text(text)
            if not isinstance(data, dict):
                continue
            deps = {
                **data.get("require", {}),
                **data.get("require-dev", {}),
            }
            dep_names = {name.lower() for name in deps}
            if "laravel/framework" in dep_names:
                detections.append(
                    Detection(
                        name="Laravel",
                        category="framework",
                        evidence=["composer.json depends on laravel/framework"],
                    )
                )
        return detections

    # ------------------------------------------------------------------
    # Ruby
    # ------------------------------------------------------------------
    def _detect_ruby_frameworks(self, context: DetectionContext) -> List[Detection]:
        detections: List[Detection] = []
        for path in context.all_detection_files():
            if Path(path).name.lower() != "gemfile":
                continue
            text = context.contents.get(path, "").lower()
            if "rails" in text:
                detections.append(
                    Detection(
                        name="Rails",
                        category="framework",
                        evidence=["Gemfile references rails"],
                    )
                )
        return detections

    # ------------------------------------------------------------------
    # Dart
    # ------------------------------------------------------------------
    def _detect_dart_frameworks(self, context: DetectionContext) -> List[Detection]:
        detections: List[Detection] = []
        for path in context.all_detection_files():
            if Path(path).name.lower() != "pubspec.yaml":
                continue
            text = context.contents.get(path, "").lower()
            if "flutter" in text:
                detections.append(
                    Detection(
                        name="Flutter",
                        category="framework",
                        evidence=["pubspec.yaml declares flutter"],
                    )
                )
        return detections

    # ------------------------------------------------------------------
    # Java
    # ------------------------------------------------------------------
    def _detect_java_frameworks(self, context: DetectionContext) -> List[Detection]:
        detections: List[Detection] = []
        for path in context.all_detection_files():
            name = Path(path).name.lower()
            if name in ("build.gradle", "build.gradle.kts"):
                text = context.contents.get(path, "").lower()
                if "spring-boot" in text or "springboot" in text:
                    detections.append(
                        Detection(
                            name="Spring Boot",
                            category="framework",
                            evidence=[f"{name} declares spring-boot"],
                        )
                    )
        return detections

    # ------------------------------------------------------------------
    # C#
    # ------------------------------------------------------------------
    def _detect_csharp_frameworks(self, context: DetectionContext) -> List[Detection]:
        detections: List[Detection] = []
        for path in context.all_detection_files():
            name = Path(path).name.lower()
            if name.endswith(".csproj"):
                text = context.contents.get(path, "").lower()
                if "aspnetcore" in text or "microsoft.aspnetcore" in text:
                    detections.append(
                        Detection(
                            name="ASP.NET Core",
                            category="framework",
                            evidence=[f"{name} references ASP.NET Core"],
                        )
                    )
        return detections
