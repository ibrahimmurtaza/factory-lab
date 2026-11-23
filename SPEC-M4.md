# SPEC-M4.md — Factory Lab M4 Task Intake and Planning Specification

**Status:** Authoritative specification (implementation-ready, not yet implemented)
**Milestone:** M4 — Task Intake and Planning
**Depends on:** M1–M3 (completed)
**Deferred to M5+:** Model provider integration, OpenCode execution, execution-plane behavior, database persistence

---

## 1. Scope

M4 introduces task intake, task lifecycle management, structured implementation planning, and human approval of plans. It does **not** include code execution, file modifications, Git operations, model provider integration, or any execution-plane behavior.

### CLI command surface

| Command | Purpose |
|---------|---------|
| `factory task create <project-id> "<description>"` | Register a task in `created` state; persist it |
| `factory task list` | List all task records |
| `factory task status <task-id>` | Concise task overview |
| `factory task show <task-id>` | Complete task record, all revisions, approvals, lifecycle history |
| `factory task plan <task-id>` | Generate an implementation plan via `TaskPlanner`; transition to `awaiting_approval` |
| `factory task approve <task-id>` | Approve the current plan revision; transition task to `approved` |
| `factory task reject <task-id> "<reason>"` | Reject the current plan revision; transition task to `rejected` |
| `factory task cancel <task-id>` | Cancel the task when the current lifecycle state permits |

`factory task run` is reserved for a future execution-capable milestone and is **not** introduced in M4.

### Out of scope for M4

- No `ModelProvider`, OpenRouter integration, API-key handling, or network dependencies
- No OpenCode execution adapter or execution-plane behavior
- No database, Redis, event-sourcing, or additional infrastructure
- No QA/review step or execution/delivery approval gates (deferred to M6)
- No automatic planning during task creation

---

## 2. Architecture and component boundaries

M4 operates entirely in the control plane. It does not import execution-plane internals.

### Component dependency structure

```
CLI (cli/commands/task.py) → TaskService (control/task.py)
TaskService → TaskStorage (control/task_storage.py)
TaskService → ProjectService (control/projects/service.py) [M2, project lookup/validation]
TaskService → ProjectProfiler (intelligence/engine.py) [M3, profiling only during plan_task]
TaskService → TaskPlanner (control/planner.py)
TaskService → ActorResolver (control/actor.py)
```

### Module organization

| Module | Responsibility |
|--------|---------------|
| `src/factory/control/task.py` | `TaskService` and task lifecycle/application workflow |
| `src/factory/control/task_models.py` | `TaskRecord`, `ImplementationPlan`, `PlanRevision`, `ApprovalRecord`, `LifecycleEvent`, `TaskStatus`, supporting dataclasses |
| `src/factory/control/task_storage.py` | `TaskStorage` protocol, `JsonTaskStorage`, serialization, atomic persistence |
| `src/factory/control/planner.py` | `TaskPlanner` protocol and `DeterministicTaskPlanner` |
| `src/factory/control/actor.py` | `ActorResolver` and actor identity resolution |
| `src/factory/cli/commands/task.py` | Typer task commands, input validation, output formatting, user-facing errors |

### Architectural constraints

- Each module has one clear responsibility.
- `TaskService` coordinates dependencies but does not implement their internal functionality.
- `TaskService` contains no JSON serialization or planning heuristics.
- `TaskPlanner` does not depend on `TaskStorage` or CLI components.
- `TaskStorage` contains no task lifecycle business logic.
- CLI commands delegate business operations to `TaskService`.
- No module-level service singleton, DI framework, Typer context injection, or re-export modules.
- Follow AGENTS.md 500-line file guideline.
- Follow existing M2/M3 naming conventions and code style.

---

## 3. Data model

### TaskStatus enum

Values: `created`, `planning`, `awaiting_approval`, `approved`, `rejected`, `cancelled`.

### TaskRecord

```python
@dataclass
class TaskRecord:
    task_id: str                      # Globally unique, "task_" prefix
    project_id: str                   # Associated registered project
    description: str                  # User-provided task description
    status: TaskStatus                # Current lifecycle state
    created_at: datetime              # Task creation timestamp
    updated_at: datetime              # Last mutation timestamp
    current_revision: int | None      # Active plan revision number; None before first plan
    plan_revisions: list[PlanRevision] # Immutable plan snapshots
    lifecycle_history: list[LifecycleEvent] # Chronological transition history
```

`current_revision` is `None` before the first successful planning operation. Revision numbering starts at 1.

Deliberately excluded from `TaskRecord`: `project_name` (resolve from registered project at display time), `approval_status` (derive from current `PlanRevision` status), `completed_at` (M4 has no completed state), `revision_id` (sequential revision numbers are sufficient).

### LifecycleEvent

```python
@dataclass
class LifecycleEvent:
    from_status: TaskStatus | None
    to_status: TaskStatus
    timestamp: datetime
    actor: str | None = None
    reason: str | None = None
```

- Records actual lifecycle transitions, not every internal operation.
- Creation records an event with `from_status=None` and `to_status=created`.
- Planning records transitions into `planning` and its resulting state.
- Approval, rejection, and cancellation record their respective transitions and actor attribution.
- Record a reason when relevant (rejection, cancellation, failure).
- Maintain chronological ordering.

### ImplementationPlan (pure plan content; no revision/approval metadata)

```python
@dataclass
class ImplementationPlan:
    summary: str
    objectives: list[str]
    requirements: list[str]
    assumptions: list[PlanAssumption]
    unresolved_questions: list[str]
    implementation_steps: list[ImplementationStep]
    affected_components: list[AffectedComponent]
    dependencies: list[PlanDependency]
    acceptance_criteria: list[str]
    testing_strategy: list[TestingStrategyItem]
    risks: list[PlanRisk]
    evidence: list[PlanEvidence]
```

### Supporting models

| Model | Fields |
|-------|--------|
| `PlanAssumption` | `description: str`, `reason: str` |
| `ImplementationStep` | `number: int`, `description: str`, `rationale: str`, `affected_components: list[str]`, `depends_on: list[int]` |
| `AffectedComponent` | `name: str`, `path: str \| None`, `purpose: str`, `evidence: list[str]` |
| `PlanDependency` | `name: str`, `reason: str`, `existing: bool \| None` |
| `TestingStrategyItem` | `category: str`, `description: str` |
| `PlanRisk` | `description: str`, `impact: str`, `mitigation: str` |
| `PlanEvidence` | `source: str`, `observation: str`, `supports: str` |

### PlanRevision (wraps ImplementationPlan with revision metadata)

```python
@dataclass
class PlanRevision:
    revision_number: int
    created_at: datetime
    status: Literal["awaiting_approval", "approved", "rejected", "superseded"]
    plan: ImplementationPlan
    approval: ApprovalRecord | None
```

### ApprovalRecord

```python
@dataclass
class ApprovalRecord:
    decision: Literal["approved", "rejected"]
    actor: str
    timestamp: datetime
    reason: str | None
```

### Revision identification

- `current_revision` is an integer starting at 1, sequential within each globally unique task.
- No separate revision IDs.
- Approval belongs to the individual `PlanRevision`, not just the task.
- Task's overall approval state remains consistent with its current revision.
- Historical approval decisions are preserved even when a revision becomes `superseded`.

### Revision immutability

- `ImplementationPlan` content is immutable once created. Plan-content models (`ImplementationPlan`, `PlanAssumption`, `ImplementationStep`, `AffectedComponent`, `PlanDependency`, `TestingStrategyItem`, `PlanRisk`, `PlanEvidence`) are frozen dataclasses where practical.
- Revision status and approval metadata may change according to the lifecycle rules, but existing `ImplementationPlan` content must never be overwritten.
- Never overwrite or mutate an existing `ImplementationPlan`.
- Replanning creates the next revision number and updates `current_revision`.
- Rejected revisions remain `rejected`.
- A previously approved revision becomes `superseded` if materially replaced; its original `ApprovalRecord` is retained.
- A new revision always starts as `awaiting_approval`.

---

## 4. Persistence layer

### Storage location

One JSON sidecar file per task under:

```
~/.factory-lab/tasks/<task-id>.json
```

### TaskStorage protocol

```python
class TaskStorage(Protocol):
    def load(self, task_id: str) -> TaskRecord | None: ...
    def save(self, task_id: str, record: TaskRecord) -> None: ...
    def list_all(self) -> list[TaskRecord]: ...
```

### JsonTaskStorage

- Implements `TaskStorage` using JSON serialization.
- Atomic writes: write to a temporary file in the same directory, then `os.replace`.
- Temporary files are cleaned up after write failures.
- Includes `schema_version` field in each persisted task record.
- Validates schema on load; malformed or unknown schema versions raise `TaskStorageError`.
- `list_all()` enumerates and deserializes valid task JSON sidecar files.
- Stored task ID must match the filename/task ID; mismatches raise `TaskStorageError`.
- Malformed or corrupted records produce controlled errors (`TaskStorageError`); corrupted records are never silently omitted.
- Failed persistence does not mutate in-memory state as if the operation succeeded.
- Serialization concerns are separate from `TaskRecord` domain fields.
- Storage abstraction is independent of the JSON representation for future database replacement at M7.

### Failure guarantees

#### JsonTaskStorage

- Atomic writes: write to a temporary file in the same directory, then `os.replace`.
- Temporary files are cleaned up after write failures.
- No partial persisted records: a save either fully replaces the target or leaves it untouched.
- Controlled storage errors: `TaskStorageError` on malformed/corrupted records, schema mismatches, or task ID/filename mismatches.

#### TaskService

- Build candidate records without mutating the loaded record until persistence succeeds.
- Only treat an operation as successful after persistence to `TaskStorage` completes.
- Preserve prior revisions, approvals, and lifecycle state on failed planning or persistence.
- Failed persistence does not mutate in-memory state as if the operation succeeded.

- Failed planning does not persist a partial revision.
- Failed replanning preserves all previous plan revisions and approvals.
- Task records survive separate CLI invocations.

---

## 5. Actor resolution

### ActorResolver

Resolves the actor in this order:

1. Read `FACTORY_LAB_ACTOR` environment variable.
2. If unset or blank, fall back to `getpass.getuser()`.
3. Trim whitespace; reject empty actor values with a clear error.
4. Raise `ActorResolutionError` only if neither `FACTORY_LAB_ACTOR` nor `getpass.getuser()` yields a valid non-empty actor.

### Usage

- `ApprovalRecord.actor` populated with resolved identity.
- Same actor recorded in relevant `LifecycleEvent` entries.
- No `--actor` CLI flag required.
- Actor not derived from task descriptions, plan content, or other untrusted input.
- No authentication, user accounts, passwords, or authorization infrastructure in M4.
- Documented as attribution, not verified authentication.
- Replaceable for future multi-user/cloud identity integration.

---

## 6. TaskService interface

### Public methods

```python
create_task(project_id: str, description: str) -> TaskRecord
list_tasks() -> list[TaskRecord]
get_task(task_id: str) -> TaskRecord
plan_task(task_id: str) -> TaskRecord
approve_task(task_id: str) -> TaskRecord
reject_task(task_id: str, reason: str) -> TaskRecord
cancel_task(task_id: str) -> TaskRecord
```

### Method responsibilities

- `create_task`: Validate input, verify the project exists via the M2 project lookup contract (`ProjectService.get_project`), generate a unique task ID, create a task in `created` state, persist it. Does not invoke `ProjectProfiler` inspection solely for task creation.
- `list_tasks`: Return all registered task records.
- `get_task`: Return the complete task record, including all revisions and historical approvals.
- `plan_task`: Retrieve task and registered project, invoke M3 `ProjectProfiler`, pass resulting `ProjectProfile` to `TaskPlanner`, validate generated plan, append new revision, transition to `awaiting_approval`.
- `approve_task`: Approve current revision, record actor attribution and timestamp, transition task to `approved`.
- `reject_task`: Reject current revision, record actor attribution, timestamp, and reason, transition task to `rejected`.
- `cancel_task`: Cancel the task when current lifecycle state permits.

### Actor resolution

`TaskService` resolves the actor internally through its injected `ActorResolver` dependency. Used for approval, rejection, and cancellation where lifecycle attribution is required. No actor parameter in public methods; no CLI `--actor` option.

### Exception hierarchy

All exceptions inherit from existing `FactoryError` (`src/factory/errors.py`):

```
TaskError
├── TaskNotFoundError
├── TaskValidationError
├── InvalidTaskTransitionError
├── ProjectNotFoundError        (reuse existing M3 exception)
├── ProjectInspectionError
├── PlanningError
├── PlanValidationError
├── ActorResolutionError
└── TaskStorageError
```

Use exception chaining when wrapping lower-level failures. Do not expose stack traces or internal implementation details through normal CLI output. Unexpected programming errors are not silently converted into domain exceptions.

### PlanValidationError acceptance criteria

- Required fields and field types validated on the `ImplementationPlan`.
- Step numbering valid and unique (each `ImplementationStep.number` is unique within the plan).
- `depends_on` references existing step numbers only.
- No self-dependencies (a step cannot depend on itself).
- No invalid dependency references (referencing a step number that does not exist).
- Invalid plans are rejected before persistence; `plan_task` raises `PlanValidationError` and no revision is written.

### CLI error mapping

- Exit code 0: success
- Exit code 1: expected `FactoryError`/application failures (stderr message)
- Exit code 2: Typer argument/parameter validation failures

---

## 7. Lifecycle rules

### Valid states and transitions

| From → To | Trigger | Condition |
|-----------|---------|-----------|
| — → `created` | `create_task` | Valid project ID and description |
| `created` → `planning` | `plan_task` (start) | Task exists |
| `planning` → `awaiting_approval` | `plan_task` (success) | Plan generated and validated |
| `planning` → `created` | `plan_task` (failure) | No partial revision persisted; state restored to pre-planning |
| `awaiting_approval` → `approved` | `approve_task` | Current revision exists |
| `awaiting_approval` → `rejected` | `reject_task` | Current revision exists; reason provided |
| `rejected` → `planning` | `plan_task` (replan) | New revision appended |
| `awaiting_approval` → `cancelled` | `cancel_task` | Cancellation permitted |
| `approved` → `planning` | `plan_task` (replan) | New revision appended; old approved revision becomes `superseded` |
| `created` → `cancelled` | `cancel_task` | Cancellation permitted |
| `rejected` → `cancelled` | `cancel_task` | Cancellation permitted |

### Invalid transitions

The following `plan_task` invocations are invalid and raise `InvalidTaskTransitionError`:

- `plan_task` on `awaiting_approval` — cannot replan while a plan awaits approval; approve or reject first.
- `plan_task` on `cancelled` — `cancelled` is terminal; no further transitions permitted.

Any transition not listed in the valid transitions table is invalid.

### Cancellation policy

| State | Cancellation allowed |
|-------|---------------------|
| `created` | Yes |
| `planning` | No |
| `awaiting_approval` | Yes |
| `approved` | Yes |
| `rejected` | Yes |
| `cancelled` | No (terminal) |

### Approved-plan replanning behavior

When `plan_task` is called on an `approved` task:

1. Generate a candidate plan via `TaskPlanner.create_plan()` without changing persisted state.
2. Compare the candidate's complete normalized `ImplementationPlan` content with the current approved revision's plan.
3. Plan equivalence excludes timestamps and revision metadata (revision number, revision status, created_at, approval).
4. If equivalent: retain the existing revision and its `ApprovalRecord`; task remains `approved`.
5. If materially different: append a new revision (starting as `awaiting_approval`), mark the previous approved revision as `superseded`, preserve its `ApprovalRecord`, and transition the task to `awaiting_approval` (fresh approval required).

Replanning a rejected task always creates a new revision; it never retains an existing rejected revision.

Task descriptions are not editable through M4 CLI commands. The description captured at `create_task` time is immutable for the lifetime of the task.

### State consistency

- Task status stays consistent with current revision status where applicable.
- `current_revision` is `None` in `created` state.
- `current_revision` points to the active `PlanRevision` in all other non-terminal states.
- Rejected is distinct from cancelled; rejected tasks can be replanned.
- Cancellation is terminal; `cancelled` tasks cannot be cancelled again or transition to any other state.
- Approval does not trigger code execution, file modifications, Git operations, or execution-plane behavior.

### Revision status transitions

| Revision status transition | Trigger |
|---------------------------|---------|
| (new) → `awaiting_approval` | Successful planning |
| `awaiting_approval` → `approved` | `approve_task` |
| `awaiting_approval` → `rejected` | `reject_task` |
| `approved` → `superseded` | Replanning replaces an approved plan |
| `rejected` → `rejected` | Remains rejected when superseded by replanning |

---

## 8. DeterministicTaskPlanner

### Input

- Task description (string)
- M3 `ProjectProfile` (languages, frameworks, infrastructure, structure, git metadata)

### Output

- Structured `ImplementationPlan`

### TaskPlanner protocol

```python
class TaskPlanner(Protocol):
    def create_plan(self, task_description: str, project_profile: ProjectProfile) -> ImplementationPlan: ...
```

`create_plan` accepts a task description and M3 `ProjectProfile`, and returns a fully populated `ImplementationPlan`. The protocol has no dependencies on `TaskStorage`, CLI components, or execution-plane code.

### Planning approach (hybrid: generic skeleton + evidence-based tech overlays)

1. **Objectives:** Derived from task description, normalized into concise outcome-oriented statements.
2. **Requirements:** Extracted from task description using deterministic rules; underspecified requirements recorded as unresolved questions.
3. **Implementation steps:** Generic six-step lifecycle:
   - Inspect existing implementation and identify extension points
   - Design around existing project conventions
   - Implement requested functionality
   - Add/update relevant tests
   - Run available validation and regression checks
   - Review changes against acceptance criteria
   Optional tech-specific overlays applied only when supported by `ProjectProfile` evidence (Python, FastAPI, Django, React, Next.js, Flutter, Docker, PostgreSQL). Documentation-only tasks do not receive implementation steps.
4. **Affected components:** Derived from `RepositoryStructure` and inspection evidence only. Repository-relative paths only when known. Never invent conventional paths.
5. **Dependencies:** `existing=true` when found in a dependency manifest; `existing=false` only with concrete justification; `existing=null` when status cannot be established. No invented packages or versions.
6. **Acceptance criteria:** Outcome-oriented and verifiable, derived from requested outcome and explicit requirements.
7. **Testing strategy:** Evidence hierarchy — existing test directories → test config → framework conventions → generic recommendations. Never assume a test runner from detection alone.
8. **Assumptions:** Only when relevant (e.g., existing architecture preserved, existing dependencies reused). No boilerplate.
9. **Unresolved questions:** Missing information that could materially change implementation decisions.
10. **Risks:** Conditional risk rules (no tests → regression risk; schema changes → migration risk; etc.). Each risk includes impact and mitigation.
11. **Evidence:** Connects repository observations to plan decisions. Every repository-specific claim has supporting evidence where available.

### Determinism and safety

- Same task description + identical `ProjectProfile` → equivalent plan content (excluding generated timestamps).
- No shell commands, code execution, network requests, or repository modifications.
- No invented file paths, package names, package versions, test commands, or architecture details.
- Unsupported technologies fall back to generic planning.
- Structurally valid `ImplementationPlan` even with incomplete repository information.
- Empty lists acceptable when no relevant information exists; no fabricated entries.
- `TaskPlanner` does not depend on `TaskStorage` or CLI components; it receives a `ProjectProfile` as input.

---

## 9. Cross-check against existing documentation

### ARCHITECTURE.md

| Existing principle | M4 alignment |
|-------------------|--------------|
| Control plane vs execution plane separation (ADR-003) | M4 is entirely control plane; no execution-plane imports |
| Runtime/provider independence (ADR-005) | No `ModelProvider`; deterministic planning only |
| Local-first/cloud-capable (ADR-001) | JSON sidecar files local; storage abstraction for future DB |
| CLI-first (ADR-002) | CLI commands are thin presentation layer |
| Modular monolith (ADR-004) | Components in `control/` package; no new package hierarchies |
| Security model | No secrets logged, no network, no code execution, project-scoped |
| System boundaries | Task intake and planning in scope; OpenCode execution initiation out of scope |

**Required update to ARCHITECTURE.md:** Add task-management and planning components to the component responsibilities table and data flow; clarify Phase 1 includes plan approval.

### PLANNING.md

| Existing statement | Required change |
|-------------------|-----------------|
| M4 depends on "model provider abstraction" | Remove; model provider integration belongs to a later milestone |
| M4 Definition of Done mentions `factory task run` | Replace with `factory task create`/`plan`/`approve`/`reject` |
| M4 does not mention plan approval | Add plan approval to M4 Definition of Done |
| M6 assigned QA & approval gates | Keep M6 for QA and execution/delivery approval gates; M4 owns plan approval |

### TASK.md

- Add M4 section mirroring the approved specification (CLI commands, data model, lifecycle, DoD).
- Remove "Task intake and execution (M4–M5)" from out-of-scope (M4 intake is in scope; execution remains M5).

### AGENTS.md

- File organization aligns with `control/task.py` and `control/planner.py` conventions.
- New modules (`task_models.py`, `task_storage.py`, `actor.py`, `cli/commands/task.py`) follow one-responsibility-per-module.
- No `.github/workflows/` modifications.

---

## 10. Edge case resolutions

### Revision status vs task status consistency

| Task status | Current revision status |
|-------------|------------------------|
| `created` | `None` |
| `planning` | New revision in progress (not yet persisted) |
| `awaiting_approval` | `awaiting_approval` |
| `approved` | `approved` |
| `rejected` | `rejected` |
| `cancelled` | Last revision retains its status (terminal) |

### Planning failure recovery

- `plan_task` transitions task to `planning` at start and records a lifecycle event.
- On planning failure: no partial revision persisted; task reverts to its exact pre-planning status; a lifecycle event records the rollback transition back to the pre-planning status; previous revisions and approvals preserved.
- On replanning failure: all previous revisions and approvals preserved; task status unchanged; lifecycle event records the failed transition.
- The persisted task state always matches the final recorded lifecycle transition.

| Original state | Recovery transition |
|---|---|
| `created` | `planning → created` |
| `rejected` | `planning → rejected` |
| `approved` | `planning → approved` |

### Corrupted/malformed task records

- `TaskStorage.load()` raises `TaskStorageError` for corrupted records.
- `TaskStorage.list_all()` raises `TaskStorageError` if any record is corrupted; never silently omits.
- `TaskService` propagates `TaskStorageError` to CLI; CLI maps to exit code 1.

### Path traversal prevention

- Task IDs are UUID-based with `task_` prefix; generated by `TaskService`, not user input.
- Task IDs are validated before use in storage paths.

### Material change to approved plan

- Calling `plan_task` on an `approved` task creates a new revision (`awaiting_approval`).
- The previous approved revision becomes `superseded`; its `ApprovalRecord` is retained.
- Task transitions to `awaiting_approval`; fresh approval required.

---

## 11. M4 Definition of Done

M4 is complete only when all the following acceptance criteria are satisfied.

### 1. Task intake and persistence

- `factory task create` creates a task in `created` state.
- Task IDs are globally unique, use the `task_` prefix, and are validated against path traversal.
- Task records persist under `~/.factory-lab/tasks/<task-id>.json`.
- Persisted records include a schema version.
- Writes are atomic using a temporary file and `os.replace`.
- `TaskStorage` implements `load`, `save`, and `list_all`.
- Tasks survive separate CLI invocations.
- Invalid or corrupted records produce controlled errors.

### 2. Task lifecycle and CLI

- All eight commands implemented: create, list, status, show, plan, approve, reject, cancel.
- Valid lifecycle transitions enforced in `TaskService`.
- Invalid transitions raise `InvalidTaskTransitionError`.
- Rejection and cancellation record appropriate reasons.
- Cancellation is terminal.
- Replanning after rejection appends a new revision.
- Historical revisions and approvals are preserved.
- `status` provides a concise overview.
- `show` displays the complete task record and revision history.
- CLI commands delegate business operations to `TaskService`.

### 3. Project profiling and deterministic planning

- `TaskService` retrieves registered project and invokes existing M3 `ProjectProfiler`.
- Missing projects raise `ProjectNotFoundError`.
- Profiling failures preserve existing revisions and approvals.
- `DeterministicTaskPlanner` implements generic skeleton and conditional technology overlays.
- Plan fields follow agreed evidence and uncertainty rules.
- Unsupported technologies fall back to generic planning.
- No invented paths, dependencies, package versions, or test commands.
- Equivalent inputs produce equivalent plan content.
- Plans validated before persistence.

### 4. Approval and actor attribution

- Successful planning creates a revision in `awaiting_approval`.
- Approval and rejection apply to the current revision.
- Approval/rejection/cancellation use internally resolved actor attribution.
- `ActorResolver` follows env-var and OS-user fallback rules.
- Failed actor resolution prevents the requested transition.
- Approval/rejection timestamps, actors, and reasons persisted.
- Replacing an approved plan preserves its historical approval and marks previous revision `superseded`.
- Plan approval does not execute code, modify repositories, or trigger Git operations.

### 5. Error handling and reliability

- Expected application errors follow `FactoryError` hierarchy.
- Expected errors map to CLI exit code 1.
- Typer argument validation retains exit code 2.
- Successful commands return exit code 0.
- Failed planning does not persist a partial revision.
- Failed replanning preserves prior revisions and approvals.
- Storage failures surfaced consistently.
- Unexpected programming errors not silently swallowed.

### 6. Architecture, testing, and documentation

- Agreed M4 module organization followed.
- `_task_service()` assembles dependencies without business logic.
- No module-level service singleton or DI framework.
- Existing M2/M3 behavior and tests remain intact.
- Unit tests cover models, serialization, storage, lifecycle transitions, planning rules, actor resolution, exceptions (assigned to implementation tickets M4-01 through M4-08).
- CLI integration tests cover all task commands and exit codes.
- Failure-path tests verify preservation of previous revisions and approvals (assigned to M4-10).
- M4-10 provides comprehensive tests of: lifecycle transition branches, planning and replanning failures, approval and rejection, actor-resolution failures, serialization and storage failures, CLI integration, and regression behavior.
- Coverage is reported for control-plane logic; meaningful gaps are documented.
- ADR-006 through ADR-010 created.
- Architecture and project documentation updated.
- No database, Redis, model API, execution runtime, or cloud infrastructure introduced.
