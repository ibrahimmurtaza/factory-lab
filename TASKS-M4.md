# TASKS-M4.md — M4 Implementation Tickets

**Status:** For review (not yet implemented)
**Dependencies:** M1–M3 complete
**Order:** Tickets must be implemented in dependency order; tests written alongside code

---

## Ticket M4-01: Domain models and exceptions

**Priority:** High  
**Dependencies:** None  
**Module:** `src/factory/control/task_models.py`, `src/factory/errors.py`

### Scope

- Define `TaskStatus` enum (`created`, `planning`, `awaiting_approval`, `approved`, `rejected`, `cancelled`).
- Define `LifecycleEvent` dataclass.
- Define `ImplementationPlan` and all supporting models (`PlanAssumption`, `ImplementationStep`, `AffectedComponent`, `PlanDependency`, `TestingStrategyItem`, `PlanRisk`, `PlanEvidence`).
- Define `PlanRevision` and `ApprovalRecord`.
- Define `TaskRecord`.
- Add exception classes to `src/factory/errors.py`: `TaskError`, `TaskNotFoundError`, `TaskValidationError`, `InvalidTaskTransitionError`, `ProjectInspectionError`, `PlanningError`, `PlanValidationError`, `ActorResolutionError`, `TaskStorageError`. Reuse `ProjectNotFoundError` from M3.

### Acceptance criteria

- All dataclasses have type hints and Google-style docstrings.
- `TaskStatus` is a proper enum with the 6 agreed values (no `failed` state).
- `PlanRevision.status` uses `Literal["awaiting_approval", "approved", "rejected", "superseded"]`.
- `ApprovalRecord.decision` uses `Literal["approved", "rejected"]`.
- All exceptions inherit from `FactoryError` (directly or via `TaskError`).
- `ProjectNotFoundError` is reused from M3 `errors.py`, not redefined.

### Tests

- Unit tests for all model constructors and field defaults.
- Unit tests for exception hierarchy and chaining.
- No network, no external processes.

---

## Ticket M4-02: ActorResolver

**Priority:** High  
**Dependencies:** None  
**Module:** `src/factory/control/actor.py`

### Scope

- Implement `ActorResolver` component.
- Resolution order: `FACTORY_LAB_ACTOR` env var → `getpass.getuser()` fallback.
- Trim whitespace; reject empty actor values.
- Raise `ActorResolutionError` when no valid actor can be resolved.
- Make resolution replaceable (e.g., injectable resolver function or subclassable class).

### Acceptance criteria

- Returns trimmed non-empty actor from env var when set.
- Falls back to OS username when env var unset or blank.
- Rejects empty/whitespace-only env var values with clear error.
- Raises `ActorResolutionError` only if neither `FACTORY_LAB_ACTOR` nor `getpass.getuser()` yields a valid non-empty actor.
- Documented as attribution, not authentication.

### Tests

- Unit tests for env var priority, fallback, trimming, empty rejection, error case.
- Mock `os.environ` and `getpass.getuser`; no real env var dependence.

---

## Ticket M4-03: TaskStorage protocol and JsonTaskStorage

**Priority:** High  
**Dependencies:** M4-01 (TaskRecord), M4-02 (ActorResolver not needed here)  
**Module:** `src/factory/control/task_storage.py`

### Scope

- Define `TaskStorage` protocol with `load(task_id) -> TaskRecord | None`, `save(task_id, record)`, `list_all() -> list[TaskRecord]`.
- Implement `JsonTaskStorage` using JSON sidecar files at `~/.factory-lab/tasks/<task-id>.json`.
- Atomic writes: tempfile in same directory + `os.replace`.
- Include `schema_version` field in persisted records.
- Serialization/deserialization separate from `TaskRecord` domain fields.
- `list_all()` enumerates and deserializes valid task JSON files.
- Malformed/corrupted records raise `TaskStorageError`; never silently omitted.

### Acceptance criteria

- `save` then `load` round-trips a `TaskRecord` correctly.
- `list_all` returns all persisted tasks.
- File write is atomic (tempfile + `os.replace`).
- Persisted record contains `schema_version`.
- Stored task ID matches filename/task ID; mismatches raise `TaskStorageError`.
- Corrupted JSON file raises `TaskStorageError` on `load`.
- `list_all` raises `TaskStorageError` if any record is corrupted; never silently omits.
- Schema validation on load; unknown schema versions raise `TaskStorageError`.
- Missing file returns `None` from `load`.
- Temporary files cleaned up after write failures.
- Failed persistence does not mutate in-memory state as if the operation succeeded.
- Storage layer contains no task lifecycle business logic.

### Tests

- Unit tests for save/load round-trip, list_all, atomic write behavior, corrupted file handling, missing file.
- Unit tests for schema validation, task ID/filename mismatch, temp file cleanup.
- Unit tests for failed-persistence state consistency (in-memory state not mutated on failure).
- Use temporary directories; no dependence on `~/.factory-lab` in tests.

---

## Ticket M4-04: TaskService — create, list, get

**Priority:** High  
**Dependencies:** M4-01, M4-03; M3 `ProjectService.get_project` for project lookup  
**Module:** `src/factory/control/task.py`

### Scope

- Implement `TaskService` with constructor accepting `TaskStorage`, `ProjectService`, `ProjectProfiler`, `TaskPlanner`, `ActorResolver`.
- `create_task(project_id, description)`: validate input, verify the project exists via `ProjectService.get_project(project_id)` (M2 contract), generate unique `task_`-prefixed ID, create `created` task, persist via `TaskStorage`. Does not invoke `ProjectProfiler` inspection solely for task creation.
- `list_tasks()`: return all tasks via `TaskStorage.list_all()`.
- `get_task(task_id)`: return full `TaskRecord` via `TaskStorage.load()`.
- Validate task IDs against path traversal before storage use.
- Lifecycle event recorded on creation (`from_status=None`, `to_status=created`).
- TaskService does not duplicate project lookup logic; reuses M2 `ProjectService.get_project`.

### Acceptance criteria

- `create_task` returns `TaskRecord` with `status=created`, `current_revision=None`.
- Task ID is globally unique with `task_` prefix.
- `list_tasks` returns `list[TaskRecord]`.
- `get_task` returns complete record with all revisions and history.
- Invalid/unregistered project ID raises `ProjectNotFoundError` via `ProjectService.get_project`.
- Path traversal attempts in task ID rejected.
- `create_task` does not invoke `ProjectProfiler`.

### Tests

- Unit tests for create/list/get with mocked `TaskStorage` and `ProjectService`.
- Unit tests for ID validation and path traversal rejection.
- Unit tests for lifecycle event recording on creation.
- Unit tests verifying `create_task` does not call `ProjectProfiler`.
- No `TaskPlanner` needed yet (mocked).

---

## Ticket M4-05: TaskService — plan_task

**Priority:** High  
**Dependencies:** M4-01, M4-03, M4-04, M4-07 (TaskPlanner), M3 `ProjectProfiler`  
**Module:** `src/factory/control/task.py`

### Scope

- `plan_task(task_id)`: retrieve task, resolve registered project via `ProjectService.get_project`, invoke `ProjectProfiler.profile(project_id)`, pass `ProjectProfile` to `TaskPlanner.create_plan()`, validate resulting `ImplementationPlan`, append new revision, transition to `awaiting_approval`.
- Transition to `planning` at start; on success transition to `awaiting_approval`; on failure revert to prior state, preserve revisions.
- Approved-plan replanning: generate candidate plan before changing persisted state; compare with current approved revision; if equivalent, retain existing revision and approval; if materially different, append new revision, mark previous approved revision `superseded`, preserve its `ApprovalRecord`, require fresh approval.
- Validate plan before persistence; raise `PlanValidationError` if invalid (required fields, step numbering, depends_on references, no self-dependencies, no invalid references).
- Missing project raises `ProjectNotFoundError`.
- Profiling failure raises `ProjectInspectionError`, preserves revisions.
- Planner failure raises `PlanningError`, no partial revision persisted.
- Revision number starts at 1, increments sequentially.

### Acceptance criteria

- `plan_task` on `created` task returns record with `status=awaiting_approval`, `current_revision=1`.
- `plan_task` on `rejected` task appends revision 2, status `awaiting_approval`.
- `plan_task` on `approved` task with equivalent candidate plan retains existing revision and approval; task remains `approved`.
- `plan_task` on `approved` task with materially different plan appends new revision, marks previous `superseded`, preserves `ApprovalRecord`, transitions to `awaiting_approval`.
- Missing project raises `ProjectNotFoundError`.
- Failed planning preserves existing revisions and approvals; no partial revision persisted.
- Failed replanning preserves prior revisions and approvals.
- `TaskService` does not import detector implementations; uses only M3 `ProjectProfiler` public contract.
- Invalid plans are rejected before persistence.

### Tests

- Unit tests with mocked `ProjectProfiler` and `TaskPlanner`.
- Test missing project, profiling failure, planner failure, invalid plan.
- Test approved-plan replanning: equivalent candidate (retain), materially different (supersede + fresh approval).
- Test revision numbering and preservation on failure.
- No network, no real repository inspection in unit tests.

---

## Ticket M4-06: TaskService — approve, reject, cancel

**Priority:** High  
**Dependencies:** M4-01, M4-02, M4-03, M4-04  
**Module:** `src/factory/control/task.py`

### Scope

- `approve_task(task_id)`: approve current revision, record `ApprovalRecord` with actor/timestamp, transition to `approved`.
- `reject_task(task_id, reason)`: reject current revision, record `ApprovalRecord` with actor/timestamp/reason, transition to `rejected`.
- `cancel_task(task_id)`: transition to `cancelled` when state permits per cancellation policy (`created`, `awaiting_approval`, `approved`, `rejected` allowed; `planning` and `cancelled` disallowed).
- Actor resolved internally via `ActorResolver`.
- Failed actor resolution raises `ActorResolutionError`, no state transition.
- Invalid transitions raise `InvalidTaskTransitionError`.
- Replacing an approved plan marks previous revision `superseded`, retains its `ApprovalRecord`.
- The persisted task state always matches the final recorded lifecycle transition.

### Acceptance criteria

- `approve_task` on `awaiting_approval` returns record with `status=approved`, current revision `status=approved`.
- `reject_task` on `awaiting_approval` returns record with `status=rejected`, current revision `status=rejected`, reason recorded.
- `cancel_task` on `created`, `awaiting_approval`, `approved`, `rejected` returns `status=cancelled`.
- `cancel_task` on `planning` raises `InvalidTaskTransitionError`.
- `cancel_task` on `cancelled` raises `InvalidTaskTransitionError`.
- Invalid transition (e.g., approve `created` task) raises `InvalidTaskTransitionError`.
- `ActorResolutionError` raised when actor cannot be resolved.
- Historical approvals preserved when revision becomes `superseded`.

### Tests

- Unit tests for approve/reject/cancel with mocked `ActorResolver` and `TaskStorage`.
- Test invalid transitions, actor resolution failure, reason recording.
- Test cancellation policy per state (allowed/disallowed).
- Test `superseded` behavior on replanning after approval.
- Test persisted state matches final lifecycle transition.

---

## Ticket M4-07: DeterministicTaskPlanner

**Priority:** High  
**Dependencies:** M4-01  
**Module:** `src/factory/control/planner.py`

### Scope

- Implement `TaskPlanner` protocol with `create_plan(task_description: str, project_profile: ProjectProfile) -> ImplementationPlan`.
- Implement `DeterministicTaskPlanner` implementing `TaskPlanner.create_plan`.
- Generic six-step implementation lifecycle skeleton.
- Task-description extraction for objectives, requirements, unresolved questions.
- Evidence-based tech overlays (Python, FastAPI, Django, React, Next.js, Flutter, Docker, PostgreSQL) — conditional, gated on `ProjectProfile` evidence.
- Affected components from `RepositoryStructure` only; no invented paths.
- Dependencies: `existing=true`/`false`/`null` from manifest evidence; no invented packages or versions.
- Acceptance criteria, testing strategy, assumptions, unresolved questions, risks, evidence per spec.
- Determinism: same inputs → equivalent plan output (excluding timestamps).
- No shell commands, code execution, network, or repo modification.
- Structurally valid plan even with incomplete evidence.

### Acceptance criteria

- `create_plan` signature matches `TaskPlanner` protocol exactly.
- Plan contains all required fields with correct types.
- Tech overlays applied only when `ProjectProfile` evidence supports them.
- No invented file paths, package names, versions, or test commands.
- Unsupported technologies fall back to generic planning.
- Empty lists acceptable when no relevant information.
- Deterministic output for equivalent inputs.

### PlanValidationError criteria (validated by TaskService before persistence)

- Required fields and field types validated on the `ImplementationPlan`.
- Step numbering valid and unique (each `ImplementationStep.number` is unique within the plan).
- `depends_on` references existing step numbers only.
- No self-dependencies (a step cannot depend on itself).
- No invalid dependency references (referencing a step number that does not exist).
- Invalid plans are rejected before persistence.

### Tests

- Unit tests for each planning component (objectives, steps, components, dependencies, acceptance, testing, risks, evidence).
- Unit tests with mock `ProjectProfile` for each supported tech overlay.
- Determinism test: same inputs produce equivalent output.
- Safety test: no invented paths/packages/commands.
- PlanValidationError tests: invalid step numbering, invalid depends_on, self-dependencies, missing required fields.
- No network, no external processes.

---

## Ticket M4-08: CLI task commands

**Priority:** High  
**Dependencies:** M4-01, M4-02, M4-03, M4-04, M4-05, M4-06, M4-07  
**Module:** `src/factory/cli/commands/task.py`

### Scope

- Implement `_task_service()` helper assembling `JsonTaskStorage`, M2 `ProjectService` (for project lookup via `get_project`), M3 `ProjectProfiler` and its required dependencies (`ConfigManager`, `RepositoryInspector`, `DetectorRegistry`), `DeterministicTaskPlanner`, and `ActorResolver`.
- Inject all assembled dependencies into `TaskService`.
- Implement 8 Typer commands: `create`, `list`, `status`, `show`, `plan`, `approve`, `reject`, `cancel`.
- Input validation (task ID format, project ID existence, non-empty description/reason).
- Output formatting for `status` (concise) and `show` (complete).
- Error handling: catch `FactoryError`, print to stderr, exit code 1.
- Typer argument validation: exit code 2.
- No business logic in CLI; delegate to `TaskService`.
- Construct service per command execution (no module-level singleton).
- Before integrating, verify actual public method signatures in the existing M2 (`ProjectService.get_project`, `ProjectService.list_projects`) and M3 (`ProjectProfiler.profile`) source; do not invent or duplicate existing APIs.

### Acceptance criteria

- All 8 commands registered under `factory task`.
- `factory task create <project-id> "<desc>"` exits 0, creates task.
- `factory task list` exits 0, lists tasks.
- `factory task status <task-id>` exits 0, prints concise overview.
- `factory task show <task-id>` exits 0, prints full record.
- `factory task plan <task-id>` exits 0 on success, transitions to `awaiting_approval`.
- `factory task approve <task-id>` exits 0, transitions to `approved`.
- `factory task reject <task-id> "<reason>"` exits 0, transitions to `rejected`.
- `factory task cancel <task-id>` exits 0 on valid states.
- Invalid transitions exit 1 with clear message.
- Missing task exits 1 with clear message.
- Typer arg validation exits 2.

### Tests

- CLI integration tests using temporary directories for all 8 commands.
- Test exit codes (0, 1, 2).
- Test error messages are user-facing and actionable.
- Test `_task_service()` is monkeypatchable.
- No network; mock `ProjectProfiler` and model-dependent components.

---

## Ticket M4-09: ADR creation and documentation updates

**Priority:** Medium  
**Dependencies:** All M4 specification decisions  
**Modules:** `docs/adr/ADR-006.md` through `ADR-010.md`; `ARCHITECTURE.md`; `PLANNING.md`; `TASK.md`; `README.md`

### Scope

- Create ADR-006 through ADR-010 (already drafted in SPEC-M4).
- Update `ARCHITECTURE.md` component responsibilities table and data flow for task management/planning; clarify Phase 1 includes plan approval.
- Update `PLANNING.md`: remove model provider from M4 prerequisites; add plan approval to M4 DoD; keep M6 for QA/execution approval gates.
- Update `TASK.md`: add M4 section; adjust out-of-scope notes.
- Update `README.md`: document `factory task` commands.
- Do not duplicate full ADR content in overview documents.
- Do not modify `.github/workflows/opencode.yml`.

### Acceptance criteria

- ADR-006 through ADR-010 exist with Context, Decision, Alternatives, Consequences, Status.
- `ARCHITECTURE.md`, `PLANNING.md`, `TASK.md`, `README.md` consistent with M4 spec.
- No contradictions between documents.
- `.github/workflows/opencode.yml` unmodified.

### Tests

- No code tests; documentation review only.

---

## Ticket M4-10: Final integration, failure-path, regression, and coverage validation

**Priority:** High  
**Dependencies:** M4-01, M4-02, M4-03, M4-04, M4-05, M4-06, M4-07, M4-08  
**Module:** `tests/control/test_task.py`, `tests/control/test_task_storage.py`, `tests/control/test_planner.py`, `tests/control/test_actor.py`, `tests/cli/test_task_commands.py`

### Scope

- Final integration tests covering end-to-end task flows using temporary directories (create → plan → approve/reject/cancel).
- Failure-path tests: verify preservation of previous revisions and approvals on failed planning/replanning; corrupted storage handling; invalid lifecycle transitions.
- Comprehensive tests of: lifecycle transition branches, planning and replanning failures, approval and rejection, actor-resolution failures, serialization and storage failures, CLI integration, and regression behavior.
- Regression: run full M2/M3 test suite to confirm no breakage.
- Coverage is reported for control-plane logic; meaningful gaps are documented.
- Tests pass without optional dependencies; no network calls.
- Does NOT duplicate unit tests already assigned to implementation tickets M4-01 through M4-08; focuses on integration and cross-cutting validation.

### Acceptance criteria

- `pytest` from repo root passes all tests (M2 regression + M4 new).
- 1 skipped (symlink on Windows) acceptable; no unexpected failures.
- Failure-path tests confirm previous revisions/approvals preserved.
- No test depends on `~/.factory-lab` real path; use temp dirs.
- No test makes network calls.
- Integration tests span multiple tickets (e.g., create → plan → approve → status → show).
- Coverage reported; meaningful gaps documented.

---

## Dependency order

```
M4-01 (models, exceptions) — independent
M4-02 (ActorResolver) → M4-01 (for ActorResolutionError)
M4-03 (TaskStorage) → M4-01 (for TaskRecord)
M4-04 (TaskService CRUD) → M4-01, M4-03; M3 ProjectService.get_project
M4-05 (TaskService plan) → M4-01, M4-03, M4-04, M4-07 (TaskPlanner); M3 ProjectProfiler
M4-06 (TaskService approve/reject/cancel) → M4-01, M4-02, M4-03, M4-04
M4-07 (DeterministicTaskPlanner) → M4-01
M4-08 (CLI commands) → M4-01, M4-02, M4-03, M4-04, M4-05, M4-06, M4-07
M4-09 (ADRs + docs) → all specification decisions
M4-10 (integration + regression) → M4-01 through M4-08

DAG: no circular dependencies; M4-05 depends on M4-07 for the concrete TaskPlanner
implementation but the TaskPlanner protocol type is defined in M4-07.
```

**Review required before implementation begins.** No code should be written until this specification and ticket set is approved.
