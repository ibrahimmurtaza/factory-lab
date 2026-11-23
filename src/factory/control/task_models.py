"""Task intake domain models.

Defines the task lifecycle status, implementation plan content, plan
revisions, approval records, lifecycle events, and the aggregate task
record. Plan-content dataclasses are frozen so that an existing
ImplementationPlan can never be overwritten or mutated after creation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional


class TaskStatus(str, Enum):
    """Task lifecycle states.

    Values:
        created: Task registered, no plan yet.
        planning: Plan generation in progress.
        awaiting_approval: Plan ready for human approval.
        approved: Plan approved by a human.
        rejected: Plan rejected by a human.
        cancelled: Task cancelled; terminal state.
    """

    CREATED = "created"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class PlanAssumption:
    """An assumption made during planning.

    Attributes:
        description: What is assumed.
        reason: Why the assumption is made.
    """

    description: str
    reason: str


@dataclass(frozen=True)
class ImplementationStep:
    """A single step in the implementation plan.

    Attributes:
        number: Sequential step number, unique within the plan.
        description: What the step does.
        rationale: Why the step is needed.
        affected_components: Names of components affected by this step.
        depends_on: Step numbers this step depends on.
    """

    number: int
    description: str
    rationale: str
    affected_components: List[str] = field(default_factory=list)
    depends_on: List[int] = field(default_factory=list)


@dataclass(frozen=True)
class AffectedComponent:
    """A component affected by the implementation.

    Attributes:
        name: Component name.
        path: Repository-relative path, if known.
        purpose: Why the component is affected.
        evidence: Supporting evidence strings.
    """

    name: str
    path: Optional[str]
    purpose: str
    evidence: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PlanDependency:
    """An external dependency required by the plan.

    Attributes:
        name: Dependency name.
        reason: Why the dependency is needed.
        existing: True if found in a manifest, False if new, None if unknown.
    """

    name: str
    reason: str
    existing: Optional[bool] = None


@dataclass(frozen=True)
class TestingStrategyItem:
    """A testing strategy recommendation.

    Attributes:
        category: Type of testing (e.g. unit, integration, e2e).
        description: What to test and how.
    """

    category: str
    description: str


@dataclass(frozen=True)
class PlanRisk:
    """A risk associated with the plan.

    Attributes:
        description: What could go wrong.
        impact: Impact severity or description.
        mitigation: How to reduce or avoid the risk.
    """

    description: str
    impact: str
    mitigation: str


@dataclass(frozen=True)
class PlanEvidence:
    """Evidence supporting a plan decision.

    Attributes:
        source: Where the evidence came from.
        observation: What was observed.
        supports: Which plan element this evidence supports.
    """

    source: str
    observation: str
    supports: str


@dataclass(frozen=True)
class ImplementationPlan:
    """Pure plan content, without revision or approval metadata.

    This dataclass is frozen so that once a plan is created, its content
    can never be overwritten or mutated. Replanning always produces a new
    plan instance rather than modifying an existing one.

    Attributes:
        summary: Concise summary of the plan.
        objectives: Outcome-oriented objectives.
        requirements: Extracted or derived requirements.
        assumptions: Assumptions made during planning.
        unresolved_questions: Missing information that could change decisions.
        implementation_steps: Ordered implementation steps.
        affected_components: Components affected by the plan.
        dependencies: External dependencies required.
        acceptance_criteria: Verifiable acceptance criteria.
        testing_strategy: Recommended testing approach.
        risks: Identified risks and mitigations.
        evidence: Supporting evidence for plan decisions.
    """

    summary: str
    objectives: List[str]
    requirements: List[str]
    assumptions: List[PlanAssumption]
    unresolved_questions: List[str]
    implementation_steps: List[ImplementationStep]
    affected_components: List[AffectedComponent]
    dependencies: List[PlanDependency]
    acceptance_criteria: List[str]
    testing_strategy: List[TestingStrategyItem]
    risks: List[PlanRisk]
    evidence: List[PlanEvidence]


@dataclass
class ApprovalRecord:
    """Records a human approval or rejection decision.

    Attributes:
        decision: "approved" or "rejected".
        actor: Identity of the person who made the decision.
        timestamp: When the decision was made.
        reason: Optional reason, required for rejection.
    """

    decision: Literal["approved", "rejected"]
    actor: str
    timestamp: datetime
    reason: Optional[str] = None


@dataclass
class PlanRevision:
    """Wraps an ImplementationPlan with revision metadata.

    Attributes:
        revision_number: Sequential number starting at 1.
        created_at: When this revision was created.
        status: Current status of this revision.
        plan: The immutable plan content.
        approval: Approval record, if any has been recorded.
    """

    revision_number: int
    created_at: datetime
    status: Literal["awaiting_approval", "approved", "rejected", "superseded"]
    plan: ImplementationPlan
    approval: Optional[ApprovalRecord] = None


@dataclass
class LifecycleEvent:
    """Records a lifecycle state transition.

    Attributes:
        from_status: Previous status, None for initial creation.
        to_status: New status after the transition.
        timestamp: When the transition occurred.
        actor: Identity of the actor, if applicable.
        reason: Optional reason for the transition.
    """

    from_status: Optional[TaskStatus]
    to_status: TaskStatus
    timestamp: datetime
    actor: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class TaskRecord:
    """Aggregate task record.

    Attributes:
        task_id: Globally unique identifier with "task_" prefix.
        project_id: Associated registered project identifier.
        description: User-provided task description (immutable).
        status: Current lifecycle state.
        created_at: When the task was created.
        updated_at: When the task was last mutated.
        current_revision: Active plan revision number, None before first plan.
        plan_revisions: Immutable plan snapshots in chronological order.
        lifecycle_history: Chronological transition history.
    """

    task_id: str
    project_id: str
    description: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    current_revision: Optional[int] = None
    plan_revisions: List[PlanRevision] = field(default_factory=list)
    lifecycle_history: List[LifecycleEvent] = field(default_factory=list)
