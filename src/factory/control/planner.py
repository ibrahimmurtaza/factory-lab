"""Task planning interfaces.

Defines the :class:`TaskPlanner` port for generating implementation plans.
The concrete :class:`DeterministicTaskPlanner` is implemented in M4-07.
"""

from __future__ import annotations

from typing import Protocol

from factory.control.task_models import ImplementationPlan
from factory.intelligence.repository.models import ProjectProfile


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
