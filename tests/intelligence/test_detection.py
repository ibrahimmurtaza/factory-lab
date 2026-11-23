"""Tests for technology detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.intelligence.detection.base import (
    DetectorRegistry,
    DetectionContext,
)
from factory.intelligence.detection.frameworks import FrameworkDetector
from factory.intelligence.detection.infrastructure import InfrastructureDetector
from factory.intelligence.detection.languages import LanguageDetector


def _context(root: Path, files, contents) -> DetectionContext:
    return DetectionContext(root=root, files=files, manifest_contents=contents)


def test_python_detection_from_files(tmp_path):
    registry = DetectorRegistry(detectors=[LanguageDetector()])
    context = _context(
        tmp_path,
        ["main.py", "utils.py", "pyproject.toml"],
        {"pyproject.toml": "[project]\nname = \"x\"\n"},
    )
    detections = registry.detect_all(context)
    names = {d.name for d in detections if d.category == "language"}
    assert "Python" in names


def test_javascript_and_typescript_detection(tmp_path):
    registry = DetectorRegistry(detectors=[LanguageDetector()])
    context = _context(
        tmp_path,
        ["index.js", "app.ts", "package.json", "tsconfig.json"],
        {
            "package.json": '{"name": "x", "devDependencies": {"typescript": "^5.0"}}',
            "tsconfig.json": '{"compilerOptions": {}}',
        },
    )
    detections = registry.detect_all(context)
    names = {d.name for d in detections if d.category == "language"}
    assert "JavaScript" in names
    assert "TypeScript" in names


def test_framework_detection_from_manifests(tmp_path):
    registry = DetectorRegistry(detectors=[FrameworkDetector()])
    context = _context(
        tmp_path,
        ["pyproject.toml"],
        {
            "pyproject.toml": '[project]\ndependencies = ["fastapi", "uvicorn"]\n',
        },
    )
    detections = registry.detect_all(context)
    names = {d.name for d in detections if d.category == "framework"}
    assert "FastAPI" in names


def test_react_and_nextjs_detection(tmp_path):
    registry = DetectorRegistry(detectors=[FrameworkDetector()])
    context = _context(
        tmp_path,
        ["package.json"],
        {
            "package.json": '{"dependencies": {"react": "^18.0", "next": "^13.0"}}',
        },
    )
    detections = registry.detect_all(context)
    names = {d.name for d in detections if d.category == "framework"}
    assert "React" in names
    assert "Next.js" in names


def test_infrastructure_detection(tmp_path):
    registry = DetectorRegistry(detectors=[InfrastructureDetector()])
    context = _context(
        tmp_path,
        ["Dockerfile", "docker-compose.yml", ".github/workflows/ci.yml", "main.tf"],
        {
            "Dockerfile": "FROM python:3.11",
            "docker-compose.yml": "services:",
            ".github/workflows/ci.yml": "name: ci",
            "main.tf": 'resource "aws_instance" "x" {}',
        },
    )
    detections = registry.detect_all(context)
    names = {d.name for d in detections if d.category == "infrastructure"}
    assert "Docker" in names
    assert "Docker Compose" in names
    assert "GitHub Actions" in names
    assert "Terraform" in names


def test_multiple_languages_in_one_repo(tmp_path):
    registry = DetectorRegistry(detectors=[LanguageDetector()])
    context = _context(
        tmp_path,
        ["main.py", "app.js", "server.go", "lib.rs", "pom.xml", "Gemfile"],
        {
            "pom.xml": "<project></project>",
            "Gemfile": "source 'https://rubygems.org'",
        },
    )
    detections = registry.detect_all(context)
    names = {d.name for d in detections if d.category == "language"}
    assert {"Python", "JavaScript", "Go", "Rust", "Java", "Ruby"}.issubset(names)


def test_unknown_technologies_do_not_fail(tmp_path):
    registry = DetectorRegistry(detectors=[LanguageDetector(), FrameworkDetector()])
    context = _context(
        tmp_path,
        ["something.xyz", "weird.unknown"],
        {},
    )
    # Should not raise.
    detections = registry.detect_all(context)
    assert isinstance(detections, list)


def test_detection_records_evidence(tmp_path):
    registry = DetectorRegistry(detectors=[FrameworkDetector()])
    context = _context(
        tmp_path,
        ["pyproject.toml"],
        {
            "pyproject.toml": '[project]\ndependencies = ["django"]\n',
        },
    )
    detections = registry.detect_all(context)
    django = [d for d in detections if d.name == "Django"]
    assert len(django) == 1
    assert len(django[0].evidence) >= 1
    assert all(isinstance(e, str) and e for e in django[0].evidence)
