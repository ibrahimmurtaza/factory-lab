"""Task planning interfaces and deterministic implementation.

Defines the :class:`TaskPlanner` port for generating implementation plans
and the concrete :class:`DeterministicTaskPlanner` implementation.

The :class:`TaskPlanner` protocol has no dependencies on :class:`TaskStorage`,
CLI components, or execution-plane code. It receives a task description
and an M3 :class:`ProjectProfile` and returns a fully populated
:class:`ImplementationPlan`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

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
from factory.intelligence.repository.models import ProjectProfile


@runtime_checkable
class TaskPlanner(Protocol):
    """Generates an implementation plan for a task.

    The protocol has no dependencies on :class:`TaskStorage`, CLI
    components, or execution-plane code. It receives a task description
    and an M3 :class:`ProjectProfile` and returns a fully populated
    :class:`ImplementationPlan`.
    """

    def create_plan(
        self, task_description: str, project_profile: ProjectProfile
    ) -> ImplementationPlan:
        """Create an implementation plan for a task.

        Args:
            task_description: The user-provided task description.
            project_profile: M3 project profile for the task's project.

        Returns:
            A fully populated :class:`ImplementationPlan`.
        """
        ...


# ---------------------------------------------------------------------------
# DeterministicTaskPlanner
# ---------------------------------------------------------------------------

# Detection names that trigger technology overlays.
_DETECTION_PYTHON = "Python"
_DETECTION_FASTAPI = "FastAPI"
_DETECTION_DJANGO = "Django"
_DETECTION_REACT = "React"
_DETECTION_NEXTJS = "Next.js"
_DETECTION_FLUTTER = "Flutter"
_DETECTION_DOCKER = "Docker"
_DETECTION_POSTGRESQL = "PostgreSQL"

# Documentation-only task keywords.
_DOC_KEYWORDS = ("readme", "document", "docs", "documentation", "changelog")


class DeterministicTaskPlanner:
    """Deterministic implementation planner.

    Produces a structurally valid :class:`ImplementationPlan` from a task
    description and an M3 :class:`ProjectProfile`. The same inputs always
    produce equivalent plan content (excluding timestamps). No shell
    commands, code execution, network requests, or repository modifications
    are performed. No file paths, package names, versions, or test commands
    are invented.
    """

    def create_plan(
        self, task_description: str, project_profile: ProjectProfile
    ) -> ImplementationPlan:
        """Create an implementation plan for a task.

        Args:
            task_description: The user-provided task description.
            project_profile: M3 project profile for the task's project.

        Returns:
            A fully populated :class:`ImplementationPlan`.
        """
        is_documentation = self._is_documentation_only(task_description)

        objectives = self._build_objectives(task_description)
        requirements = self._build_requirements(task_description)
        assumptions = self._build_assumptions(task_description, project_profile)
        unresolved_questions = self._build_unresolved_questions(
            task_description, project_profile
        )
        implementation_steps = self._build_implementation_steps(
            task_description, project_profile, is_documentation
        )
        affected_components = self._build_affected_components(project_profile)
        dependencies = self._build_dependencies(task_description, project_profile)
        acceptance_criteria = self._build_acceptance_criteria(task_description)
        testing_strategy = self._build_testing_strategy(project_profile)
        risks = self._build_risks(project_profile)
        evidence = self._build_evidence(project_profile)

        return ImplementationPlan(
            summary=task_description.strip(),
            objectives=objectives,
            requirements=requirements,
            assumptions=assumptions,
            unresolved_questions=unresolved_questions,
            implementation_steps=implementation_steps,
            affected_components=affected_components,
            dependencies=dependencies,
            acceptance_criteria=acceptance_criteria,
            testing_strategy=testing_strategy,
            risks=risks,
            evidence=evidence,
        )

    # ------------------------------------------------------------------
    # Detection helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detection_names(detections) -> set[str]:
        """Return the set of detection names from a list of detections."""
        return {detection.name for detection in detections}

    @staticmethod
    def _is_documentation_only(task_description: str) -> bool:
        """Return True if the task description indicates documentation-only work."""
        lowered = task_description.lower()
        return any(keyword in lowered for keyword in _DOC_KEYWORDS)

    @staticmethod
    def _manifest_names(project_profile: ProjectProfile) -> set[str]:
        """Return dependency manifest filenames from repository structure."""
        return set(project_profile.structure.dependency_manifests)

    # ------------------------------------------------------------------
    # Plan section builders
    # ------------------------------------------------------------------

    def _build_objectives(self, task_description: str) -> list:
        """Derive outcome-oriented objectives from the task description."""
        desc = task_description.strip()
        return [f"Implement: {desc}"]

    def _build_requirements(self, task_description: str) -> list:
        """Extract or derive requirements from the task description."""
        desc = task_description.strip()
        return [desc] if desc else []

    def _build_assumptions(
        self, task_description: str, project_profile: ProjectProfile
    ) -> list:
        """Record assumptions only when relevant; no boilerplate."""
        assumptions: list = []
        if project_profile.structure.source_dirs:
            assumptions.append(
                PlanAssumption(
                    description="Existing source directory conventions will be preserved",
                    reason="Minimizes refactoring risk and keeps changes consistent",
                )
            )
        if project_profile.detections:
            assumptions.append(
                PlanAssumption(
                    description="Detected technologies and dependencies are reusable",
                    reason="Detection is based on repository manifests and file contents",
                )
            )
        return assumptions

    def _build_unresolved_questions(
        self, task_description: str, project_profile: ProjectProfile
    ) -> list:
        """Identify missing information that could change implementation decisions."""
        questions: list = []
        if not project_profile.structure.dependency_manifests:
            questions.append(
                "No dependency manifest found; package requirements cannot be confirmed"
            )
        if not project_profile.structure.test_dirs:
            questions.append(
                "No test directory detected; testing strategy is a generic recommendation"
            )
        if not project_profile.structure.source_dirs:
            questions.append(
                "No source directory detected; affected components are uncertain"
            )
        return questions

    def _build_implementation_steps(
        self,
        task_description: str,
        project_profile: ProjectProfile,
        is_documentation: bool,
    ) -> list:
        """Build the generic six-step lifecycle plus tech overlays."""
        if is_documentation:
            return []

        steps: list = []
        step_number = 1

        # Generic six-step lifecycle.
        generic_steps = [
            (
                "Inspect existing implementation and identify extension points",
                "Understand the current codebase before making changes",
            ),
            (
                "Design around existing project conventions",
                "Ensure new code matches established patterns",
            ),
            (
                "Implement requested functionality",
                "Deliver the user-visible behavior described in the task",
            ),
            (
                "Add or update relevant tests",
                "Verify the implemented functionality with tests",
            ),
            (
                "Run available validation and regression checks",
                "Confirm no regressions are introduced",
            ),
            (
                "Review changes against acceptance criteria",
                "Confirm the plan outcomes are satisfied",
            ),
        ]
        for description, rationale in generic_steps:
            steps.append(
                ImplementationStep(
                    number=step_number,
                    description=description,
                    rationale=rationale,
                    affected_components=[],
                    depends_on=list(range(1, step_number)),
                )
            )
            step_number += 1

        # Tech overlays, gated on ProjectProfile evidence.
        languages = self._detection_names(project_profile.languages)
        frameworks = self._detection_names(project_profile.frameworks)
        infrastructure = self._detection_names(project_profile.infrastructure)

        overlay_steps = self._tech_overlay_steps(
            languages, frameworks, infrastructure, step_number
        )
        steps.extend(overlay_steps)

        return steps

    def _tech_overlay_steps(
        self,
        languages: set,
        frameworks: set,
        infrastructure: set,
        start_number: int,
    ) -> list:
        """Return tech-specific overlay steps, ordered deterministically."""
        steps: list = []
        number = start_number

        if _DETECTION_PYTHON in languages:
            steps.append(
                ImplementationStep(
                    number=number,
                    description="Set up Python virtual environment and install dependencies",
                    rationale="Provides an isolated environment for Python development",
                    affected_components=[],
                    depends_on=list(range(1, number)),
                )
            )
            number += 1

        if _DETECTION_FASTAPI in frameworks:
            steps.append(
                ImplementationStep(
                    number=number,
                    description="Define FastAPI route handlers and Pydantic models",
                    rationale="Implements the API layer using the detected FastAPI framework",
                    affected_components=[],
                    depends_on=list(range(1, number)),
                )
            )
            number += 1

        if _DETECTION_DJANGO in frameworks:
            steps.append(
                ImplementationStep(
                    number=number,
                    description="Define Django models and views",
                    rationale="Implements the data and presentation layers using Django",
                    affected_components=[],
                    depends_on=list(range(1, number)),
                )
            )
            number += 1

        if _DETECTION_REACT in frameworks:
            steps.append(
                ImplementationStep(
                    number=number,
                    description="Create React components and page routing",
                    rationale="Builds the frontend UI using the detected React framework",
                    affected_components=[],
                    depends_on=list(range(1, number)),
                )
            )
            number += 1

        if _DETECTION_NEXTJS in frameworks:
            steps.append(
                ImplementationStep(
                    number=number,
                    description="Create Next.js pages and API routes",
                    rationale="Implements full-stack features using Next.js",
                    affected_components=[],
                    depends_on=list(range(1, number)),
                )
            )
            number += 1

        if _DETECTION_FLUTTER in frameworks:
            steps.append(
                ImplementationStep(
                    number=number,
                    description="Create Flutter widgets and state management",
                    rationale="Builds the cross-platform UI using Flutter",
                    affected_components=[],
                    depends_on=list(range(1, number)),
                )
            )
            number += 1

        if _DETECTION_DOCKER in infrastructure:
            steps.append(
                ImplementationStep(
                    number=number,
                    description="Create Dockerfile and container configuration",
                    rationale="Enables containerized builds and deployments",
                    affected_components=[],
                    depends_on=list(range(1, number)),
                )
            )
            number += 1

        if _DETECTION_POSTGRESQL in infrastructure:
            steps.append(
                ImplementationStep(
                    number=number,
                    description="Design database schema and add migration scripts",
                    rationale="Supports persistent data storage using PostgreSQL",
                    affected_components=[],
                    depends_on=list(range(1, number)),
                )
            )
            number += 1

        return steps

    def _build_affected_components(
        self, project_profile: ProjectProfile
    ) -> list:
        """Derive affected components from RepositoryStructure only; no invented paths."""
        components: list = []
        structure = project_profile.structure

        for source_dir in sorted(structure.source_dirs):
            components.append(
                AffectedComponent(
                    name=source_dir,
                    path=source_dir,
                    purpose="Contains source code affected by the implementation",
                    evidence=["repository structure inspection"],
                )
            )

        for config_file in sorted(structure.config_files):
            components.append(
                AffectedComponent(
                    name=config_file,
                    path=config_file,
                    purpose="Configuration file that may require updates",
                    evidence=["repository structure inspection"],
                )
            )

        return components

    def _build_dependencies(
        self, task_description: str, project_profile: ProjectProfile
    ) -> list:
        """Build dependencies from detection and manifest evidence.

        existing=True when found in a dependency manifest; existing=False only
        with concrete justification; existing=None when status cannot be
        established. No invented packages or versions.
        """
        dependencies: list = []
        manifest_names = self._manifest_names(project_profile)

        seen: set = set()

        def add(name: str, reason: str, existing) -> None:
            if name in seen:
                return
            seen.add(name)
            dependencies.append(
                PlanDependency(name=name, reason=reason, existing=existing)
            )

        # Add detected technologies as dependencies where evidence supports them.
        # existing=True when dependency manifests exist (detections were found
        # via manifest analysis); existing=None when status cannot be established.
        have_manifests = bool(manifest_names)
        all_detections = (
            list(project_profile.languages)
            + list(project_profile.frameworks)
            + list(project_profile.infrastructure)
        )
        for detection in all_detections:
            existing = True if have_manifests else None
            add(
                detection.name,
                f"Detected {detection.category} in project profile",
                existing,
            )

        return dependencies

    def _build_acceptance_criteria(self, task_description: str) -> list:
        """Derive outcome-oriented, verifiable acceptance criteria."""
        desc = task_description.strip()
        return [
            f"The requested functionality ({desc}) is implemented and verified",
            "All existing tests continue to pass",
            "No regressions are introduced in dependent components",
        ]

    def _build_testing_strategy(
        self, project_profile: ProjectProfile
    ) -> list:
        """Recommend testing based on repository evidence; never assume a runner."""
        strategy: list = []
        structure = project_profile.structure

        if structure.test_dirs:
            strategy.append(
                TestingStrategyItem(
                    category="unit",
                    description=f"Run existing tests in: {', '.join(sorted(structure.test_dirs))}",
                )
            )
        else:
            strategy.append(
                TestingStrategyItem(
                    category="unit",
                    description="Add unit tests for new functionality",
                )
            )

        if structure.dependency_manifests:
            strategy.append(
                TestingStrategyItem(
                    category="dependency",
                    description="Verify dependencies listed in manifests are installed",
                )
            )

        return strategy

    def _build_risks(self, project_profile: ProjectProfile) -> list:
        """Identify conditional risks with impact and mitigation."""
        risks: list = []
        structure = project_profile.structure

        if not structure.test_dirs:
            risks.append(
                PlanRisk(
                    description="No test directory detected",
                    impact="Regressions may go undetected",
                    mitigation="Add unit tests for all new functionality",
                )
            )

        if not structure.dependency_manifests:
            risks.append(
                PlanRisk(
                    description="No dependency manifest found",
                    impact="Package requirements cannot be confirmed",
                    mitigation="Create a dependency manifest before installing packages",
                )
            )

        if project_profile.structure.git_present:
            risks.append(
                PlanRisk(
                    description="Changes may conflict with existing branches",
                    impact="Merge conflicts could delay delivery",
                    mitigation="Create a feature branch and rebase frequently",
                )
            )

        return risks

    def _build_evidence(self, project_profile: ProjectProfile) -> list:
        """Connect repository observations to plan decisions."""
        evidence: list = []
        structure = project_profile.structure

        if structure.top_level_files:
            evidence.append(
                PlanEvidence(
                    source="repository structure",
                    observation=f"Top-level files: {', '.join(sorted(structure.top_level_files))}",
                    supports="project layout and entry points",
                )
            )

        if structure.dependency_manifests:
            evidence.append(
                PlanEvidence(
                    source="dependency manifests",
                    observation=f"Manifests: {', '.join(sorted(structure.dependency_manifests))}",
                    supports="declared dependencies",
                )
            )

        all_detections = (
            list(project_profile.languages)
            + list(project_profile.frameworks)
            + list(project_profile.infrastructure)
        )
        if all_detections:
            names = ", ".join(sorted(d.name for d in all_detections))
            evidence.append(
                PlanEvidence(
                    source="technology detection",
                    observation=f"Detected technologies: {names}",
                    supports="tech overlay selection",
                )
            )

        return evidence
