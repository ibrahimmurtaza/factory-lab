"""Infrastructure and tooling detectors based on repository files."""

from __future__ import annotations

from pathlib import Path
from typing import List

from factory.intelligence.detection.base import (
    Detector,
    Detection,
    DetectionContext,
    parse_json,
)

# Infrastructure evidence keyed by detection name.
INFRASTRUCTURE_RULES: dict[str, List[str]] = {
    "Docker": ["Dockerfile"],
    "Docker Compose": ["docker-compose.yml", "docker-compose.yaml"],
    "Kubernetes": [".kube", "k8s", "kubernetes"],
    "Terraform": ["*.tf"],
    "GitHub Actions": [".github/workflows"],
    "GitLab CI": [".gitlab-ci.yml"],
    "Supabase": ["supabase"],
    "PostgreSQL": ["postgresql", "psycopg2", "pg"],
    "Redis": ["redis"],
}


class InfrastructureDetector(Detector):
    """Detects infrastructure and tooling evidence from repository files."""

    @property
    def category(self) -> str:
        return "infrastructure"

    def detect(self, context: DetectionContext) -> List[Detection]:
        detections: List[Detection] = []

        # File-based evidence (exact filenames / directory names / globs).
        detections.extend(self._detect_file_based(context))

        # Content-based evidence from manifests (e.g. redis in package.json).
        detections.extend(self._detect_manifest_content(context))

        return detections

    def _detect_file_based(self, context: DetectionContext) -> List[Detection]:
        detections: List[Detection] = []
        file_names = {Path(p).name.lower() for p in context.files}
        dir_names = {
            p.split("/", 1)[0].lower() for p in context.files if "/" in p
        }

        rules = {
            "Docker": ["dockerfile"],
            "Docker Compose": ["docker-compose.yml", "docker-compose.yaml"],
            "GitLab CI": [".gitlab-ci.yml"],
        }
        for name, filenames in rules.items():
            if any(f in file_names for f in filenames):
                detections.append(
                    Detection(
                        name=name,
                        category="infrastructure",
                        evidence=[f"repository contains {f}" for f in filenames if f in file_names],
                    )
                )

        # Directory-based rules.
        dir_rules = {
            "Kubernetes": [".kube", "k8s", "kubernetes"],
            "GitHub Actions": [".github"],
            "Supabase": ["supabase"],
            "Terraform": [],  # handled by glob below
        }
        for name, dirs in dir_rules.items():
            if any(d in dir_names for d in dirs):
                evidence = [
                    f"directory: {d}"
                    for d in dirs
                    if d in dir_names
                ]
                detections.append(
                    Detection(name=name, category="infrastructure", evidence=evidence)
                )

        # GitHub Actions workflow files specifically under .github/workflows.
        has_workflows = any(
            p.lower().startswith(".github/workflows/")
            and (p.lower().endswith(".yml") or p.lower().endswith(".yaml"))
            for p in context.files
        )
        if has_workflows:
            detections.append(
                Detection(
                    name="GitHub Actions",
                    category="infrastructure",
                    evidence=[".github/workflows/ contains workflow files"],
                )
            )

        # Terraform glob *.tf.
        terraform_files = [
            p for p in context.files if Path(p).suffix.lower() == ".tf"
        ]
        if terraform_files:
            detections.append(
                Detection(
                    name="Terraform",
                    category="infrastructure",
                    evidence=[f"file: {p}" for p in terraform_files[:5]],
                )
            )

        return detections

    def _detect_manifest_content(self, context: DetectionContext) -> List[Detection]:
        detections: List[Detection] = []
        content_rules = {
            "PostgreSQL": ["postgresql", "psycopg2", "asyncpg", "pg"],
            "Redis": ["redis"],
        }
        for path in context.all_detection_files():
            text = context.contents.get(path, "").lower()
            if not text:
                continue
            for name, keywords in content_rules.items():
                found = [kw for kw in keywords if kw in text]
                if found:
                    detections.append(
                        Detection(
                            name=name,
                            category="infrastructure",
                            evidence=[
                                f"manifest {Path(path).name} references {kw}"
                                for kw in found
                            ],
                        )
                    )
        return detections
