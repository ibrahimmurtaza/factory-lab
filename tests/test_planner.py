"""Tests for DeterministicTaskPlanner (M4-07).

Uses mock ProjectProfile objects; no network, no external processes.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from factory.control.planner import DeterministicTaskPlanner
from factory.control.task_models import (
    AffectedComponent,
    ImplementationPlan,
    ImplementationStep,
    PlanAssumption,
    PlanDependency,
    PlanEvidence,
    PlanRisk,
    TestingStrategyItem,
)
from factory.errors import PlanValidationError
from factory.intelligence.repository.models import (
    Detection,
    GitMetadata,
    ProjectProfile,
    RepositoryStructure,
)


def _make_profile(
    languages=None,
    frameworks=None,
    infrastructure=None,
    structure=None,
    detections=None,
    git_metadata=None,
) -> ProjectProfile:
    return ProjectProfile(
        project_id="proj-1",
        project_name="test-proj",
        repository_root="/tmp/test-proj",
        inspected_at="2026-01-01T00:00:00+00:00",
        languages=languages or [],
        frameworks=frameworks or [],
        infrastructure=infrastructure or [],
        structure=structure or RepositoryStructure(root="/tmp/test-proj"),
        git_metadata=git_metadata,
        detections=detections or [],
    )


def _detection(name: str, category: str, evidence=None) -> Detection:
    return Detection(name=name, category=category, evidence=evidence or [])


def _planner() -> DeterministicTaskPlanner:
    return DeterministicTaskPlanner()


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_planner_implements_task_planner_protocol():
    from factory.control.planner import TaskPlanner

    planner = _planner()
    assert isinstance(planner, TaskPlanner)


def test_create_plan_signature_matches_protocol():
    import inspect

    sig = inspect.signature(DeterministicTaskPlanner.create_plan)
    params = list(sig.parameters.keys())
    assert params == ["self", "task_description", "project_profile"]
    assert sig.return_annotation is not None


# ---------------------------------------------------------------------------
# Plan structure
# ---------------------------------------------------------------------------


def test_plan_contains_all_required_fields():
    planner = _planner()
    profile = _make_profile()
    plan = planner.create_plan("add a new feature", profile)

    assert isinstance(plan, ImplementationPlan)
    assert plan.summary == "add a new feature"
    assert isinstance(plan.objectives, list)
    assert isinstance(plan.requirements, list)
    assert isinstance(plan.assumptions, list)
    assert isinstance(plan.unresolved_questions, list)
    assert isinstance(plan.implementation_steps, list)
    assert isinstance(plan.affected_components, list)
    assert isinstance(plan.dependencies, list)
    assert isinstance(plan.acceptance_criteria, list)
    assert isinstance(plan.testing_strategy, list)
    assert isinstance(plan.risks, list)
    assert isinstance(plan.evidence, list)


def test_plan_fields_have_correct_types():
    planner = _planner()
    profile = _make_profile()
    plan = planner.create_plan("implement authentication", profile)

    assert all(isinstance(o, str) for o in plan.objectives)
    assert all(isinstance(r, str) for r in plan.requirements)
    assert all(isinstance(a, PlanAssumption) for a in plan.assumptions)
    assert all(isinstance(q, str) for q in plan.unresolved_questions)
    assert all(isinstance(s, ImplementationStep) for s in plan.implementation_steps)
    assert all(isinstance(c, AffectedComponent) for c in plan.affected_components)
    assert all(isinstance(d, PlanDependency) for d in plan.dependencies)
    assert all(isinstance(c, str) for c in plan.acceptance_criteria)
    assert all(isinstance(t, TestingStrategyItem) for t in plan.testing_strategy)
    assert all(isinstance(r, PlanRisk) for r in plan.risks)
    assert all(isinstance(e, PlanEvidence) for e in plan.evidence)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_deterministic_output_for_equivalent_inputs():
    planner = _planner()
    profile = _make_profile(
        languages=[_detection("Python", "language")],
        frameworks=[_detection("FastAPI", "framework")],
        infrastructure=[_detection("Docker", "infrastructure")],
        structure=RepositoryStructure(
            root="/tmp/proj",
            dependency_manifests=["pyproject.toml"],
            test_dirs=["tests"],
            source_dirs=["src"],
        ),
    )

    plan1 = planner.create_plan("add user login", profile)
    plan2 = planner.create_plan("add user login", profile)

    assert plan1.summary == plan2.summary
    assert plan1.objectives == plan2.objectives
    assert plan1.requirements == plan2.requirements
    assert plan1.implementation_steps == plan2.implementation_steps
    assert plan1.dependencies == plan2.dependencies
    assert plan1.acceptance_criteria == plan2.acceptance_criteria
    assert plan1.testing_strategy == plan2.testing_strategy
    assert plan1.risks == plan2.risks
    assert plan1.evidence == plan2.evidence


def test_different_descriptions_produce_different_plans():
    planner = _planner()
    profile = _make_profile()
    plan1 = planner.create_plan("add feature A", profile)
    plan2 = planner.create_plan("add feature B", profile)
    assert plan1.summary != plan2.summary


# ---------------------------------------------------------------------------
# Empty inputs
# ---------------------------------------------------------------------------


def test_empty_profile_produces_valid_plan():
    planner = _planner()
    profile = _make_profile()
    plan = planner.create_plan("do something", profile)

    # Generic six-step lifecycle is always present for non-documentation tasks.
    assert len(plan.implementation_steps) == 6
    assert plan.affected_components == []
    assert plan.dependencies == []
    # Generic testing recommendation is added even with no test dirs.
    assert len(plan.testing_strategy) >= 1
    # Risks are conditional (no tests, no manifest).
    assert len(plan.risks) >= 1
    assert plan.evidence == []


def test_empty_description_produces_valid_plan():
    planner = _planner()
    profile = _make_profile()
    plan = planner.create_plan("", profile)

    assert isinstance(plan, ImplementationPlan)
    assert plan.summary == ""


# ---------------------------------------------------------------------------
# Tech overlays - Python
# ---------------------------------------------------------------------------


def test_python_overlay_adds_venv_step():
    planner = _planner()
    profile = _make_profile(languages=[_detection("Python", "language")])
    plan = planner.create_plan("add a feature", profile)

    step_descriptions = [s.description for s in plan.implementation_steps]
    assert any("Python virtual environment" in d for d in step_descriptions)


def test_python_not_detected_no_venv_step():
    planner = _planner()
    profile = _make_profile()
    plan = planner.create_plan("add a feature", profile)

    step_descriptions = [s.description for s in plan.implementation_steps]
    assert not any("Python virtual environment" in d for d in step_descriptions)


# ---------------------------------------------------------------------------
# Tech overlays - FastAPI
# ---------------------------------------------------------------------------


def test_fastapi_overlay_adds_route_step():
    planner = _planner()
    profile = _make_profile(frameworks=[_detection("FastAPI", "framework")])
    plan = planner.create_plan("add an endpoint", profile)

    step_descriptions = [s.description for s in plan.implementation_steps]
    assert any("FastAPI route handlers" in d for d in step_descriptions)


# ---------------------------------------------------------------------------
# Tech overlays - Django
# ---------------------------------------------------------------------------


def test_django_overlay_adds_models_step():
    planner = _planner()
    profile = _make_profile(frameworks=[_detection("Django", "framework")])
    plan = planner.create_plan("add a model", profile)

    step_descriptions = [s.description for s in plan.implementation_steps]
    assert any("Django models and views" in d for d in step_descriptions)


# ---------------------------------------------------------------------------
# Tech overlays - React
# ---------------------------------------------------------------------------


def test_react_overlay_adds_components_step():
    planner = _planner()
    profile = _make_profile(frameworks=[_detection("React", "framework")])
    plan = planner.create_plan("add a UI", profile)

    step_descriptions = [s.description for s in plan.implementation_steps]
    assert any("React components" in d for d in step_descriptions)


# ---------------------------------------------------------------------------
# Tech overlays - Next.js
# ---------------------------------------------------------------------------


def test_nextjs_overlay_adds_pages_step():
    planner = _planner()
    profile = _make_profile(frameworks=[_detection("Next.js", "framework")])
    plan = planner.create_plan("add a page", profile)

    step_descriptions = [s.description for s in plan.implementation_steps]
    assert any("Next.js pages" in d for d in step_descriptions)


# ---------------------------------------------------------------------------
# Tech overlays - Flutter
# ---------------------------------------------------------------------------


def test_flutter_overlay_adds_widgets_step():
    planner = _planner()
    profile = _make_profile(frameworks=[_detection("Flutter", "framework")])
    plan = planner.create_plan("add a screen", profile)

    step_descriptions = [s.description for s in plan.implementation_steps]
    assert any("Flutter widgets" in d for d in step_descriptions)


# ---------------------------------------------------------------------------
# Tech overlays - Docker
# ---------------------------------------------------------------------------


def test_docker_overlay_adds_dockerfile_step():
    planner = _planner()
    profile = _make_profile(infrastructure=[_detection("Docker", "infrastructure")])
    plan = planner.create_plan("containerize", profile)

    step_descriptions = [s.description for s in plan.implementation_steps]
    assert any("Dockerfile" in d for d in step_descriptions)


# ---------------------------------------------------------------------------
# Tech overlays - PostgreSQL
# ---------------------------------------------------------------------------


def test_postgresql_overlay_adds_schema_step():
    planner = _planner()
    profile = _make_profile(infrastructure=[_detection("PostgreSQL", "infrastructure")])
    plan = planner.create_plan("add storage", profile)

    step_descriptions = [s.description for s in plan.implementation_steps]
    assert any("database schema" in d for d in step_descriptions)


# ---------------------------------------------------------------------------
# Unsupported technologies fall back to generic planning
# ---------------------------------------------------------------------------


def test_unsupported_technology_falls_back_to_generic():
    planner = _planner()
    profile = _make_profile(
        frameworks=[_detection("UnknownFramework", "framework")]
    )
    plan = planner.create_plan("add a feature", profile)

    # Should still have generic steps but no overlay-specific steps.
    assert len(plan.implementation_steps) >= 6
    step_descriptions = [s.description for s in plan.implementation_steps]
    assert not any("UnknownFramework" in d for d in step_descriptions)


# ---------------------------------------------------------------------------
# Documentation-only tasks
# ---------------------------------------------------------------------------


def test_documentation_only_task_has_no_implementation_steps():
    planner = _planner()
    profile = _make_profile()
    plan = planner.create_plan("update the README documentation", profile)

    assert plan.implementation_steps == []


def test_documentation_only_task_detects_readme_keyword():
    planner = _planner()
    profile = _make_profile()
    plan = planner.create_plan("write docs for the API", profile)

    assert plan.implementation_steps == []


def test_non_documentation_task_has_implementation_steps():
    planner = _planner()
    profile = _make_profile()
    plan = planner.create_plan("implement user authentication", profile)

    assert len(plan.implementation_steps) > 0


# ---------------------------------------------------------------------------
# Affected components from RepositoryStructure only
# ---------------------------------------------------------------------------


def test_affected_components_from_source_dirs():
    planner = _planner()
    profile = _make_profile(
        structure=RepositoryStructure(
            root="/tmp/proj", source_dirs=["src", "lib"]
        )
    )
    plan = planner.create_plan("add a feature", profile)

    component_names = [c.name for c in plan.affected_components]
    assert "src" in component_names
    assert "lib" in component_names
    # All paths come from structure, no invented paths.
    for c in plan.affected_components:
        assert c.path is not None


def test_affected_components_from_config_files():
    planner = _planner()
    profile = _make_profile(
        structure=RepositoryStructure(
            root="/tmp/proj", config_files=["pyproject.toml", "setup.cfg"]
        )
    )
    plan = planner.create_plan("add a feature", profile)

    component_names = [c.name for c in plan.affected_components]
    assert "pyproject.toml" in component_names
    assert "setup.cfg" in component_names


# ---------------------------------------------------------------------------
# Dependencies from manifest evidence
# ---------------------------------------------------------------------------


def test_dependency_existing_true_when_in_manifest():
    planner = _planner()
    profile = _make_profile(
        languages=[_detection("Python", "language")],
        structure=RepositoryStructure(
            root="/tmp/proj", dependency_manifests=["pyproject.toml"]
        ),
    )
    plan = planner.create_plan("add a feature", profile)

    python_dep = next(
        (d for d in plan.dependencies if d.name == "Python"), None
    )
    assert python_dep is not None
    assert python_dep.existing is True


def test_dependency_existing_none_when_no_manifest():
    planner = _planner()
    profile = _make_profile(
        languages=[_detection("Python", "language")],
        structure=RepositoryStructure(root="/tmp/proj"),
    )
    plan = planner.create_plan("add a feature", profile)

    python_dep = next(
        (d for d in plan.dependencies if d.name == "Python"), None
    )
    assert python_dep is not None
    assert python_dep.existing is None


def test_no_invented_packages_or_versions():
    planner = _planner()
    profile = _make_profile()
    plan = planner.create_plan("add a feature", profile)

    for dep in plan.dependencies:
        # Dependency names should come from detections, not invented.
        assert dep.name  # non-empty
        assert dep.version is None if hasattr(dep, "version") else True
        # No version strings in dependency names.
        assert not any(char.isdigit() for char in dep.name)


# ---------------------------------------------------------------------------
# Testing strategy from structure
# ---------------------------------------------------------------------------


def test_testing_strategy_uses_existing_test_dirs():
    planner = _planner()
    profile = _make_profile(
        structure=RepositoryStructure(root="/tmp/proj", test_dirs=["tests"])
    )
    plan = planner.create_plan("add a feature", profile)

    categories = [t.category for t in plan.testing_strategy]
    assert "unit" in categories
    assert any("tests" in t.description for t in plan.testing_strategy)


def test_testing_strategy_generic_when_no_test_dirs():
    planner = _planner()
    profile = _make_profile(structure=RepositoryStructure(root="/tmp/proj"))
    plan = planner.create_plan("add a feature", profile)

    assert any(t.category == "unit" for t in plan.testing_strategy)


# ---------------------------------------------------------------------------
# Risks
# ---------------------------------------------------------------------------


def test_risk_no_tests():
    planner = _planner()
    profile = _make_profile(structure=RepositoryStructure(root="/tmp/proj"))
    plan = planner.create_plan("add a feature", profile)

    assert any("No test directory" in r.description for r in plan.risks)


def test_risk_no_manifest():
    planner = _planner()
    profile = _make_profile(structure=RepositoryStructure(root="/tmp/proj"))
    plan = planner.create_plan("add a feature", profile)

    assert any("No dependency manifest" in r.description for r in plan.risks)


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


def test_evidence_includes_detected_technologies():
    planner = _planner()
    profile = _make_profile(
        languages=[_detection("Python", "language")],
        frameworks=[_detection("FastAPI", "framework")],
    )
    plan = planner.create_plan("add a feature", profile)

    assert any("Detected technologies" in e.observation for e in plan.evidence)


# ---------------------------------------------------------------------------
# PlanValidationError criteria (validated by TaskService)
# ---------------------------------------------------------------------------


def test_plan_step_numbers_unique():
    planner = _planner()
    profile = _make_profile()
    plan = planner.create_plan("add a feature", profile)

    step_numbers = [s.number for s in plan.implementation_steps]
    assert len(step_numbers) == len(set(step_numbers))


def test_plan_no_self_dependencies():
    planner = _planner()
    profile = _make_profile()
    plan = planner.create_plan("add a feature", profile)

    for step in plan.implementation_steps:
        assert step.number not in step.depends_on


def test_plan_depends_on_references_existing_steps():
    planner = _planner()
    profile = _make_profile()
    plan = planner.create_plan("add a feature", profile)

    step_numbers = {s.number for s in plan.implementation_steps}
    for step in plan.implementation_steps:
        for dep in step.depends_on:
            assert dep in step_numbers


def test_plan_summary_non_empty_when_description_non_empty():
    planner = _planner()
    profile = _make_profile()
    plan = planner.create_plan("implement the feature", profile)

    assert plan.summary.strip() != ""


# ---------------------------------------------------------------------------
# Generic six-step lifecycle
# ---------------------------------------------------------------------------


def test_generic_six_step_lifecycle():
    planner = _planner()
    profile = _make_profile()
    plan = planner.create_plan("implement the feature", profile)

    descriptions = [s.description for s in plan.implementation_steps]
    assert any("Inspect existing implementation" in d for d in descriptions)
    assert any("Design around existing project conventions" in d for d in descriptions)
    assert any("Implement requested functionality" in d for d in descriptions)
    assert any("Add or update relevant tests" in d for d in descriptions)
    assert any("Run available validation" in d for d in descriptions)
    assert any("Review changes against acceptance criteria" in d for d in descriptions)


def test_generic_steps_have_sequential_numbers():
    planner = _planner()
    profile = _make_profile()
    plan = planner.create_plan("implement the feature", profile)

    numbers = [s.number for s in plan.implementation_steps]
    assert numbers == list(range(1, len(numbers) + 1))


# ---------------------------------------------------------------------------
# Frozen plan content
# ---------------------------------------------------------------------------


def test_plan_content_models_are_frozen():
    plan = ImplementationPlan(
        summary="s",
        objectives=[],
        requirements=[],
        assumptions=[],
        unresolved_questions=[],
        implementation_steps=[],
        affected_components=[],
        dependencies=[],
        acceptance_criteria=[],
        testing_strategy=[],
        risks=[],
        evidence=[],
    )
    with pytest.raises(FrozenInstanceError):
        plan.summary = "changed"
