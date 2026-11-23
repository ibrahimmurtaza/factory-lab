"""Base types and helpers for technology detection."""

from __future__ import annotations

import json
import tomllib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Iterable, List, Set

from factory.intelligence.repository.models import Detection

__all__ = [
    "DetectionContext",
    "Detector",
    "DetectorRegistry",
    "read_text_file",
]


class DetectionContext:
    """Raw observations gathered by the repository inspector."""

    def __init__(
        self,
        root: Path,
        files: Iterable[str],
        manifest_contents: Dict[str, str],
    ) -> None:
        self.root = root
        self.files: Set[str] = set(files)
        self.contents: Dict[str, str] = dict(manifest_contents)

    def has_file(self, *names: str) -> bool:
        """Return True if any of ``names`` (exact relative paths) exists."""
        return any(name in self.files for name in names)

    def has_file_named(self, *basenames: str) -> bool:
        """Return True if any file with one of the given basenames exists."""
        for file_path in self.files:
            if Path(file_path).name.lower() in {n.lower() for n in basenames}:
                return True
        return False

    def file_contains(self, path: str, substring: str) -> bool:
        """Return True if the manifest at ``path`` contains ``substring``."""
        return substring.lower() in self.contents.get(path, "").lower()

    def manifest_contains_dependency(self, path: str, dependency: str) -> bool:
        """Heuristic dependency check for text-based manifests."""
        return self.file_contains(path, dependency)

    def all_detection_files(self) -> List[str]:
        """Return manifest paths whose contents were captured."""
        return sorted(self.contents.keys())


class Detector(ABC):
    """Abstract base for a technology detector.

    Each detector is responsible for one category of technology and returns
    detections with supporting evidence. Detectors never modify the
    repository and never perform network or shell operations.
    """

    @property
    @abstractmethod
    def category(self) -> str:
        """The detection category: 'language', 'framework', or 'infrastructure'."""

    @abstractmethod
    def detect(self, context: DetectionContext) -> List[Detection]:
        """Detect technologies in ``context`` and return detections."""


class DetectorRegistry:
    """Runs a collection of detectors and aggregates their results."""

    def __init__(self, detectors: Iterable[Detector]) -> None:
        self._detectors = list(detectors)

    def detect_all(self, context: DetectionContext) -> List[Detection]:
        """Run every detector and return combined detections."""
        detections: List[Detection] = []
        for detector in self._detectors:
            try:
                detections.extend(detector.detect(context))
            except Exception:
                # A single detector must never break inspection.
                continue
        return detections


def read_text_file(path: Path) -> str:
    """Read a text file safely, returning an empty string on failure."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def parse_json(path: Path) -> object:
    """Parse a JSON file, returning None on failure."""
    try:
        return json.loads(read_text_file(path))
    except (ValueError, TypeError):
        return None


def parse_json_text(text: str) -> object:
    """Parse a JSON document string, returning None on failure."""
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def parse_toml(path: Path) -> dict:
    """Parse a TOML file, returning an empty dict on failure."""
    try:
        with path.open("rb") as binary:
            return tomllib.load(binary)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def parse_toml_text(text: str) -> dict:
    """Parse a TOML document string, returning an empty dict on failure."""
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}
