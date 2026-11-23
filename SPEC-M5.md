# SPEC-M5.md — Factory Lab M5 Execution Orchestration & Coding Runtime Integration

**Status:** Authoritative specification (implementation-ready, not yet implemented)
**Milestone:** M5 — Execution Orchestration & Coding Runtime Integration
**Depends on:** M1–M4 (completed)
**Deferred to M6+:** QA/review step, execution/delivery approval gates beyond pre-dispatch, database persistence, OS-level sandboxing, cloud workers, GitHub PR creation

---

## 1. Scope

M5 introduces execution of approved implementation plans through a replaceable coding runtime, initially OpenCode. Execution operates in the execution plane behind the `CodingRuntime` interface; no OpenCode imports enter the control plane.

M5 is responsible for:

- Orchestrating the execution of an approved `ImplementationPlan` step-by-step against a registered project.
- Isolating execution in a Git worktree per attempt.
- Invoking OpenCode as a subprocess CLI adapter, never importing OpenCode internals in orchestration.
- Tracking execution attempts independently of the M4 task lifecycle.
- Enforcing pre-dispatch, operation-specific human approval for sensitive operations.
- Capturing logs, artifacts, and test results per execution attempt.
- Delivering completed work to the original repository via an explicit feature-branch delivery flow.
- Preserving failed and interrupted executions for inspection; no automatic resume.

M5 does **not** include:

- OS-level process sandboxing (worktree isolation is not a security sandbox).
- Resume of a terminated OpenCode process from where it stopped.
- Automatic merging into the original branch.
- GitHub pull request creation.
- Database persistence (M7).
- Cloud worker infrastructure (the `ExecutionEnvironment` interface preserves the path, but no cloud implementation).
- QA/review step running tests/lint after implementation (M6).
- Modification of M4 `TaskStatus`, `TaskRecord`, or task-planning behavior.

---

## 2. Architecture and component boundaries

M5 spans the control plane and the execution plane, communicating through interfaces per ADR-003 and ADR-005.

### Component dependency structure

```
CLI (cli/commands/task.py) → TaskService (control/task.py) [M4, unchanged]
TaskService → ExecutionService (control/execution.py) [M5, new]
ExecutionService → CodingRuntime interface (control/runtime.py) [M5, new]
CodingRuntime → OpenCodeAdapter (execution/adapter_opencode.py) [M5, new]
OpenCodeAdapter → OpenCode subprocess CLI [external process]
ExecutionService → ExecutionEnvironment interface (control/environment.py) [M5, new]
ExecutionEnvironment → LocalProcessEnvironment (execution/environment.py) [M5, new]
ExecutionService → ExecutionStorage (control/execution_storage.py) [M5, new]
ExecutionService → WorktreeManager (execution/git.py) [M5, new]
WorktreeManager → Git CLI [external process]
```

### Module organization

| Module | Responsibility |
|--------|---------------|
| `src/factory/control/runtime.py` | `CodingRuntime` protocol and `ExecutionResult` domain model |
| `src/factory/control/environment.py` | `ExecutionEnvironment` protocol |
| `src/factory/control/execution.py` | `ExecutionService` application workflow |
| `src/factory/control/execution_storage.py` | `ExecutionStorage` protocol and `JsonExecutionStorage` |
| `src/factory/control/execution_models.py` | `ExecutionRecord`, `ExecutionStatus`, `ExecutionStepStatus`, `ExecutionStepResult`, `ApprovalDecision` |
| `src/factory/execution/adapter_opencode.py` | OpenCode subprocess adapter implementing `CodingRuntime` |
| `src/factory/execution/environment.py` | `LocalProcessEnvironment` implementing `ExecutionEnvironment` |
| `src/factory/execution/git.py` | Git worktree creation/cleanup/inspection wrapper |
| `src/factory/cli/commands/task.py` | M5 additions: `run`, `logs`, `deliver`, `cleanup`, `executions`, `reconcile` |

### Architectural constraints

- Each module has one clear responsibility.
- `ExecutionService` coordinates dependencies but does not implement their internal functionality.
- `ExecutionService` contains no subprocess, Git, or JSON serialization logic.
- `CodingRuntime` and `ExecutionEnvironment` have no dependencies on `ExecutionStorage` or CLI components.
- `ExecutionStorage` contains no execution lifecycle business logic.
- CLI commands delegate business operations to `ExecutionService`.
- No module-level service singleton, DI framework, Typer context injection, or re-export modules.
- No OpenCode-specific types or imports in the control plane.
- Follow AGENTS.md 500-line file guideline.
- Follow existing M2/M3/M4 naming conventions and code style.
- M4 `TaskRecord`, `TaskStatus`, `TaskService`, and task CLI commands remain unchanged.

---

## 3. Data model

### ExecutionStatus enum (execution-level)

Values: `queued`, `running`, `completed`, `failed`, `paused`.

- `queued`: Execution record created, awaiting dispatch.
- `running`: OpenCode subprocess actively executing a step.
- `completed`: All approved steps executed successfully.
- `failed`: OpenCode exited non-zero, was interrupted, or an unrecoverable error occurred.
- `paused`: Factory Lab-controlled checkpoint awaiting pre-dispatch approval; never implies suspend/resume of a running process.

### ExecutionStepStatus enum (step-level)

Values: `queued`, `running`, `completed`, `failed`, `paused`.

- Step-level status tracks the lifecycle of an individual implementation step within an execution.
- `queued`: Step awaiting dispatch.
- `running`: OpenCode subprocess executing this step.
- `completed`: Step finished successfully (exit code 0).
- `failed`: Step exited non-zero, was interrupted, or errored.
- `paused`: Step awaiting pre-dispatch approval before dispatch.

### ApprovalDecision

```python
@dataclass(frozen=True)
class ApprovalDecision:
    operation: str              # Human-readable operation (e.g. "install dependencies")
    reason: str                 # Why the operation is needed
    affected_resources: list[str] # Repository-relative paths or resource identifiers
    approved: bool              # Whether the human approved this specific operation
    actor: str                  # Who made the decision
    timestamp: datetime         # When the decision was made
    execution_attempt: int      # Which execution attempt this decision applies to
```

### ExecutionRecord

```python
@dataclass
class ExecutionRecord:
    exec_id: str              # Globally unique, "exec_" prefix
    task_id: str              # Associated task (must exist and be approved)
    plan_revision: int        # Exact approved plan revision being executed
    attempt_number: int       # Execution attempt number for this task (1, 2, ...)
    status: ExecutionStatus   # Current execution-level lifecycle state
    created_at: datetime      # Record creation timestamp
    updated_at: datetime      # Last mutation timestamp
    started_at: datetime | None   # First transition to running
    completed_at: datetime | None # Transition to completed/failed
    worktree_path: str | None     # Absolute path to the Git worktree working directory
    worktree_metadata_dir: str | None # Absolute path to Git's internal worktree metadata
    branch_name: str | None       # Worktree branch name
    exit_code: int | None         # OpenCode exit code for the last step, if any
    interruption_reason: str | None # Reason if interrupted (e.g. Ctrl+C)
    error_message: str | None     # Terminal failure message, if failed
    subprocess_pid: int | None    # PID of the OpenCode subprocess, if launched
    process_started_at: datetime | None # When the subprocess started, if known
    process_confirmed_stopped: bool | None # True if process termination was confirmed
    approval_decisions: list[ApprovalDecision] # Persisted operation-specific approvals
    step_results: list[ExecutionStepResult] # Per-step results in order
```

### ExecutionStepResult

```python
@dataclass(frozen=True)
class ExecutionStepResult:
    step_number: int          # Matches ImplementationStep.number
    status: ExecutionStepStatus # Step-level lifecycle state
    started_at: datetime | None
    completed_at: datetime | None
    exit_code: int | None
    output: str               # Captured stdout/stderr from OpenCode subprocess (redacted)
    artifacts: list[str]      # Relative paths to captured artifacts
    test_results: list[str]   # Relative paths to captured test results
    scope_violations: list[str] # Detected out-of-scope changes, if any
```

### ExecutionResult (adapter return type)

```python
@dataclass
class ExecutionResult:
    step_number: int
    status: ExecutionStepStatus # completed or failed from adapter perspective
    exit_code: int
    output: str               # Opaque stdout + stderr combined (redacted)
    artifacts: list[str]      # Discovered artifact paths
    test_results: list[str]   # Discovered test result paths
    scope_violations: list[str] # Detected out-of-scope changes
    subprocess_pid: int | None      # PID of the OpenCode subprocess, if launched
    process_started_at: datetime | None # When the subprocess started, if known
    process_confirmed_stopped: bool | None # True if process termination was confirmed
```

### Process observation contract

The `CodingRuntime` adapter owns subprocess management: it launches the OpenCode subprocess, observes its PID and start time, and reports termination. `execute_step` accepts an optional `observe` callback:

```python
Callable[[int | None, datetime | None, bool | None], None]
```

- The callback receives `(subprocess_pid, process_started_at, process_confirmed_stopped)`.
- The adapter invokes `observe` with the subprocess PID and start time **while the OpenCode subprocess is running**, before execution completes.
- The adapter invokes `observe` with termination confirmation (`process_confirmed_stopped`) when the OpenCode subprocess exits.
- `ExecutionResult` carries `subprocess_pid`, `process_started_at`, and `process_confirmed_stopped` back to `ExecutionService` as the final step result.
- `ExecutionService` owns persistence and is solely responsible for writing these fields to the `ExecutionRecord`. Process metadata (`subprocess_pid`, `process_started_at`) is persisted before the OpenCode subprocess terminates so it remains available for crash reconciliation if Factory Lab crashes while OpenCode is running; `process_confirmed_stopped` is persisted at termination.
- The adapter must not depend on `ExecutionStorage` or call persistence directly; observations are delivered only through the `observe` callback and `ExecutionResult`.
- PID and process-start metadata are treated as reconciliation evidence, not conclusive proof that a process is alive or dead.

`current_revision` on `TaskRecord` remains unchanged; execution status is entirely separate from task status. `ExecutionRecord` references `task_id` and `plan_revision` to bind an execution to a specific approved plan revision. Execution-level status is distinct from step-level status: the execution is `running` while any step is `running`; the execution is `completed` only when all steps are `completed`.

---

## 4. Persistence layer

### Storage location

One JSON sidecar file per execution attempt under:

```
~/.factory-lab/executions/<exec-id>.json
```

Per-execution directory:

```
~/.factory-lab/executions/<exec-id>/
  logs/
  artifacts/
  test-results/
```

### ExecutionStorage protocol

```python
class ExecutionStorage(Protocol):
    def load(self, exec_id: str) -> ExecutionRecord | None: ...
    def save(self, exec_id: str, record: ExecutionRecord) -> None: ...
    def list_all(self) -> list[ExecutionRecord]: ...
    def list_for_task(self, task_id: str) -> list[ExecutionRecord]: ...
```

### JsonExecutionStorage

- Implements `ExecutionStorage` using JSON serialization, following the M4 `JsonTaskStorage` pattern.
- Atomic writes: temporary file in the same directory, then `os.replace`.
- Temporary files cleaned up after write failures.
- Includes `schema_version` field in each persisted execution record.
- Validates schema on load; malformed or unknown schema versions raise `ExecutionStorageError`.
- `list_all()` enumerates and deserializes valid execution JSON sidecar files.
- `list_for_task(task_id)` returns all executions for a task, sorted by creation time descending.
- Stored exec ID must match filename/exec ID; mismatches raise `ExecutionStorageError`.
- Malformed or corrupted records produce controlled errors (`ExecutionStorageError`); corrupted records are never silently omitted.
- Failed persistence does not mutate in-memory state as if the operation succeeded.
- Serialization concerns are separate from `ExecutionRecord` domain fields.
- Storage abstraction is independent of the JSON representation for future database replacement at M7.

### Failure guarantees

#### JsonExecutionStorage

- Atomic writes: tempfile in same directory + `os.replace`.
- No partial persisted records: a save either fully replaces the target or leaves it untouched.
- Controlled storage errors: `ExecutionStorageError` on malformed/corrupted records, schema mismatches, or exec ID/filename mismatches.

#### ExecutionService

- Build candidate records without mutating the loaded record until persistence succeeds.
- Only treat an operation as successful after persistence to `ExecutionStorage` completes.
- Preserve prior step results and execution state on failed dispatch or persistence.
- Failed persistence does not mutate in-memory state as if the operation succeeded.
- **Initial running-state persistence:** `ExecutionService` must persist the execution record in `running` state (with worktree path and branch) before launching the OpenCode subprocess. If that persistence fails, OpenCode must not be launched; the execution remains in a safe pre-dispatch state and the failure is reported to the user.
- **Failed step evidence:** A step that exits non-zero, is interrupted, or errors must still have its failure result persisted: `step_number`, `status=failed`, `exit_code`, redacted `output`, `started_at`/`completed_at` timestamps, and any available artifact references. A failed step is not silently discarded and is not represented as a successful or partial success state transition.
- **OpenCode executed but subsequent persistence fails:** If OpenCode has executed and produced output but persistence of the step result or execution record fails, `ExecutionService` must preserve the recoverable output (logs, redacted output, artifact references) and report the execution state as potentially stale. The user must be alerted that the persisted state may not reflect the actual subprocess outcome.
- A storage failure must never be represented as a successful state transition.
- Execution records survive separate CLI invocations.

---

## 5. CodingRuntime and ExecutionEnvironment interfaces

### CodingRuntime protocol

```python
from typing import Callable
from datetime import datetime

class CodingRuntime(Protocol):
    def execute_step(
        self,
        step: ImplementationStep,
        plan: ImplementationPlan,
        worktree_path: Path,
        environment: dict[str, str],
        observe: Callable[[int | None, datetime | None, bool | None], None] | None = None,
    ) -> ExecutionResult: ...
```

`execute_step` accepts a single implementation step, the full approved plan for context, the path to the execution worktree working directory, and an allowlisted environment dictionary. It returns a structured `ExecutionResult`. The adapter owns subprocess management: it launches OpenCode, observes its PID and start time, and reports termination via `ExecutionResult.subprocess_pid`, `process_started_at`, and `process_confirmed_stopped`. `ExecutionService` owns persistence of those fields.

### ExecutionEnvironment protocol

```python
class ExecutionEnvironment(Protocol):
    def prepare(self, worktree_path: Path) -> dict[str, str]: ...
    def cleanup(self, worktree_path: Path) -> None: ...
```

`prepare` returns the allowlisted environment variables for a subprocess in the given worktree working directory. `cleanup` releases environment resources associated with a worktree.

### LocalProcessEnvironment (M5 implementation)

- Returns an allowlisted subset of environment variables for subprocess execution.
- Allowlist is configurable in Factory Lab configuration.
- Default allowlist includes essential platform variables: `PATH`, `HOME`/`USERPROFILE`, `SYSTEMROOT` where applicable, `TEMP` and `TMP`.
- OpenCode credentials and provider API keys must be explicitly opted in by variable name; never persisted.
- Does not inherit the full caller environment.
- No cloud infrastructure; local process only.

---

## 6. OpenCode subprocess adapter

### Adapter responsibilities

- Implement `CodingRuntime` by invoking the OpenCode CLI as a subprocess.
- Pass the approved step description and plan context to OpenCode via stdin/args.
- Set the subprocess working directory to the execution worktree working directory.
- Use the allowlisted environment from `ExecutionEnvironment.prepare`.
- Record the subprocess PID and process-started timestamp in the execution record.
- Capture opaque stdout/stderr plus exit code; do not rely on an unconfirmed OpenCode structured event protocol.
- Detect scope violations by comparing changed files in the worktree against `affected_components` paths (post-hoc diff review, not prevention).
- Return a structured `ExecutionResult` built from exit code, output, discovered artifacts, test results, and scope violations.
- Never import OpenCode-specific types or libraries into the control plane.

### Output handling

- Capture stdout and stderr as opaque text.
- Redact known secret environment-variable values, common API-key patterns, bearer tokens, authorization headers, and identifiable credential formats before persisting captured output.
- Never write environment values or secrets to execution logs.
- Document that redaction cannot guarantee detection of every secret.
- Treat OpenCode output as observability, not as a security enforcement mechanism.

---

## 7. Git worktree creation and isolation

### Worktree paths (three distinct paths)

M5 distinguishes three paths per execution:

1. **Worktree working directory**: The actual Git worktree where OpenCode executes. Located in a deterministic directory adjacent to the registered repository (not inside `.git/worktrees`).
2. **Git's internal worktree metadata directory**: Git's internal bookkeeping for the worktree (e.g., `.git/worktrees/<name>/`). Managed by Git; Factory Lab reads but does not place its working directory here.
3. **Execution artifact directory**: `~/.factory-lab/executions/<exec-id>/` with `logs/`, `artifacts/`, `test-results/`. Independent of the worktree.

### Worktree lifecycle

- One Git worktree per execution attempt.
- Worktree working directory name: `factory-lab-<task-id>-<attempt>`, located adjacent to the registered repository.
- Worktree checked out from the project's current branch at execution start.
- **Path collision handling:** Before creating a worktree working directory, `WorktreeManager` must verify that no directory with the target name already exists. If a collision is detected, Factory Lab must not overwrite or reuse the existing directory; it must either increment the attempt number to derive a non-colliding name or fail with a clear, actionable error. The existing directory is never touched.
- Worktree retained after execution (success or failure) until user acknowledges delivery or runs `cleanup`.
- Factory Lab never auto-merges worktree changes into the original branch.
- Worktree isolation organizes Git working directories but is **not** a filesystem security sandbox; OpenCode may still access files outside the worktree.

### WorktreeManager responsibilities

- Create a worktree working directory in the deterministic adjacent location.
- Return the worktree working directory path, Git metadata directory path, and branch name.
- Inspect changed files in the worktree (for scope enforcement).
- Remove a worktree working directory (only when terminal and `--force` or uncommitted changes absent; never for active/running executions).
- Never modify the original repository branch except through the explicit `deliver` flow.

---

## 8. Sequential, dependency-aware step dispatch

### Dispatch model

- Approved `ImplementationPlan.implementation_steps` are dispatched strictly sequentially in step-number order.
- Each step's `depends_on` references earlier step numbers; M5 respects this ordering by dispatching in sequence.
- No parallel execution in M5; step N+1 begins only after step N reaches a terminal state (`completed` or `failed`).
- A step that fails (`failed`) halts the entire execution; subsequent steps remain `queued` and are not dispatched.
- Each step dispatches exactly one OpenCode `execute_step` call.

### Step state transitions

- Execution awaiting a pre-dispatch approval decision: `paused`.
- Step awaiting pre-dispatch approval: `queued` (it has not started).
- Approval granted: execution returns to `running`; the step becomes `running` when dispatched.
- `queued` → `running` (before dispatch).
- `running` → `completed` (OpenCode exit code 0).
- `running` → `failed` (OpenCode non-zero exit, interruption, or error).
- `queued` → `paused` (awaiting pre-dispatch approval for a sensitive operation).
- Approval rejected: the step remains undispatched (`queued`); execution follows the failure/rejection behavior specified in Section 13.
- `paused` never means suspending or resuming an already-running OpenCode process.

### Plan validation before dispatch

Before dispatching any step, `ExecutionService` validates the plan's dependency graph:

- Missing dependency: a `depends_on` references a step number that does not exist in the plan → reject.
- Invalid reference: a step depends on itself → reject.
- Forward dependency: a step depends on a higher-numbered step → reject (steps must depend only on earlier steps).
- Cycle: any circular dependency among steps → reject.
- Empty plan: an approved `ImplementationPlan` with zero `implementation_steps` is rejected before dispatch; no worktree is created and no OpenCode subprocess is launched.
- Invalid plans are rejected before dispatch; no worktree is created and no OpenCode subprocess is launched.

---

## 9. Scope enforcement against `affected_components`

### Allowed scope

- The approved plan's `affected_components` defines the repository-relative paths that execution may modify.
- OpenCode is instructed (via prompt/context) to limit changes to affected components.

### Enforcement (detective, not preventive)

- After each step, inspect changed files in the worktree working directory.
- Scope inspection accounts for: added files, modified files, deleted files, renamed files, untracked files.
- Normalize repository-relative paths; safely handle path traversal and symlinks.
- Compare changed file paths against `affected_components` paths.
- Record any out-of-scope changes as `scope_violations` on the step result.
- Reject delivery if out-of-scope changes are detected.
- **Limitation:** Worktree isolation does not technically prevent writes outside affected components; scope violations are detected post-hoc via diff review, not blocked at write time.

---

## 10. Operation-specific pre-dispatch approvals

### Sensitive operations requiring approval

Before dispatching a step that involves any of the following, Factory Lab must obtain explicit human approval:

- Dependency installation (package managers, `pip install`, `npm install`, etc.).
- Network-dependent commands.
- Destructive Git operations (force push, reset, branch deletion).
- File writes outside the approved `affected_components`.

### Approval semantics

- Approval is tied to a specific execution attempt, operation, and affected resources.
- Approval decisions and their scope are persisted in the `ExecutionRecord.approval_decisions` list.
- Approval applies only to the identified operation and execution attempt.
- Approval does not automatically authorize unrelated sensitive operations.
- Unanticipated sensitive operations are denied wherever interception is available; never silently permitted.
- If a sensitive operation cannot be safely handled without runtime interaction, the step stops and requires a new approval decision.
- Do not grant blanket permission for an entire step or execution.
- `paused` status represents awaiting a pre-dispatch approval checkpoint; it does not imply suspend/resume of a running OpenCode process.

### Pre-dispatch approval vs runtime enforcement

- Pre-dispatch approval is a Factory Lab-side human decision recorded before dispatching a step. It is recorded in `ExecutionRecord.approval_decisions`.
- Runtime enforcement means restricting the OpenCode subprocess through tool restrictions, operating-system mechanisms, or other enforceable controls wherever technically possible and where a verified capability exists.
- Prompt instructions, an approval record, and post-hoc diff review are **not** security boundaries and do **not** prevent an operation. They are observability and detective controls only.
- Factory Lab does not invent an OpenCode permission capability. Any runtime restriction capability requires verification as an implementation constraint; if no verified capability exists, Factory Lab must not claim that pre-dispatch approval protects against the operation.
- Where Factory Lab cannot reliably intercept or restrict an operation, the limitation is explicitly documented, and execution is not represented as securely controlled against that operation.

---

## 11. Environment-variable allowlisting and output redaction

### Environment allowlist

- Configurable in Factory Lab configuration.
- Default allowlist includes essential platform variables: `PATH`, `HOME`/`USERPROFILE`, `SYSTEMROOT` where applicable, `TEMP` and `TMP`.
- OpenCode credentials and provider API keys must be explicitly opted in by variable name.
- Never persist secret values.
- The OpenCode subprocess receives only the allowlisted environment variables, not the full caller environment.

### Output redaction

- Redact known secret environment-variable values, common API-key patterns, bearer tokens, authorization headers, and identifiable credential formats before persisting captured output.
- Document that redaction cannot guarantee detection of every secret.
- Environment values are never written to execution logs.

---

## 12. Execution logs, artifacts, and test-result directories

### Directory structure

Each execution gets:

```
~/.factory-lab/executions/<exec-id>/
  logs/          # Captured OpenCode stdout/stderr per step (redacted)
  artifacts/     # Discovered build/output artifacts
  test-results/  # Discovered test execution results
```

### Preservation guarantees

- Logs, artifacts, and test results are captured per step and stored in the execution directory.
- Failed executions preserve all partial output for inspection.
- A failed step must retain its failure result, exit code, redacted output, timestamps, and available artifact references.
- A failed execution must preserve partial logs and artifacts.
- Artifacts and execution records outlive worktree cleanup; removed only by explicit user action.
- Artifact deletion remains a separate deferred capability; not part of M5.
- No secrets in logs (per ADR-014 redaction rules).
- Do not silently discard partial execution evidence.

---

## 13. Failure handling and interruption

### OpenCode failure

- OpenCode non-zero exit code → step marked `failed`, execution marked `failed`, subsequent steps not dispatched.
- Failure reason and exit code recorded on the step result and execution record.
- Worktree, logs, artifacts, and partial changes retained for inspection.
- User must replan from a new approved revision to retry; no automatic resume.

### Interruption (Ctrl+C / process signal)

- Factory Lab attempts graceful termination of the OpenCode subprocess.
- Execution marked `failed` with an interruption reason recorded.
- Worktree and artifacts preserved.
- No resume semantics.

### M5 does not resume

- A terminated OpenCode process cannot be resumed from where it stopped.
- Users replan from a new approved revision after failure or interruption.

---

## 14. Crash detection and reconciliation

### Factory Lab crash during execution

- If Factory Lab crashes while OpenCode is running, the OpenCode process may be orphaned.
- The execution record remains in `running` state on disk with `subprocess_pid`, `process_started_at`, and `process_confirmed_stopped` fields populated where available.
- No automatic reconciliation or process reaping on restart.
- No automatic marking of `running` executions as `failed` solely because a record is still `running` after restart.
- `subprocess_pid`, `process_started_at`, and `process_confirmed_stopped` are treated as **evidence** for reconciliation, not conclusive proof by themselves.
- Never infer that a process is dead solely from a potentially reused PID.
- Explicit user confirmation is required before marking an uncertain execution `failed`.
- `factory task reconcile <exec-id>` is included if reliable cross-platform implementation is feasible (Windows and Linux); otherwise document the manual confirmation workflow and limitations.
- A paused execution has no running OpenCode subprocess under the M5 model, but it is still non-terminal.

---

## 15. Execution history and CLI commands

### New M5 CLI commands

| Command | Purpose |
|---------|---------|
| `factory task run <task-id>` | Execute the approved plan for a task; creates an execution attempt |
| `factory task logs <task-id>` | Return execution output for the latest attempt |
| `factory task executions <task-id>` | List all execution attempts for a task |
| `factory task deliver <exec-id>` | Stage and commit worktree changes; cherry-pick into a feature branch in the original repository |
| `factory task cleanup <exec-id>` | Remove a worktree/execution (refuses unless `--force`; never for active/running) |
| `factory task reconcile <exec-id>` | Confirm process state and mark uncertain executions failed (if implemented) |

### CLI behavior

- `factory task run <task-id>`: verifies task is `approved`, creates `ExecutionRecord` in `queued`, validates plan dependencies, creates worktree, dispatches steps sequentially, persists execution record and step results.
- `factory task logs <task-id>`: prints captured output for the latest execution attempt.
- `factory task executions <task-id>`: distinct command listing all attempts with exec ID, status, plan revision, attempt number, and timestamps.
- `factory task status <task-id>`: shows task status plus latest execution attempt status.
- `factory task show <task-id>`: includes task and execution details, including approval decisions and step results.

### Exit codes

- Exit code 0: success.
- Exit code 1: expected application failure (stderr message).
- Exit code 2: Typer argument/parameter validation failure.

---

## 16. Delivery through explicit confirmation, feature branches and cherry-picking

### `factory task deliver <exec-id>` workflow

`deliver` operates only on executions with execution-level status `completed`.

1. Inspect the execution worktree diff.
2. Display changed files and a summary.
3. Require explicit user confirmation before any write to the original repository.
4. Stage and commit intended execution changes in the worktree working directory.
5. Create a feature branch in the original repository (e.g., `factory-lab/<task-id>/<exec-id>`).
6. Cherry-pick the execution commit into that branch.
7. Stop safely on cherry-pick conflicts, preserving the worktree and execution commit.

### Cherry-pick failure recovery

If cherry-pick fails after the destination feature branch has been created:
- Preserve the execution worktree working directory and the execution commit.
- Do not delete or rewrite the destination branch; report its resulting state (e.g., branch created but cherry-pick not applied, or partially applied) to the user.
- The user must resolve conflicts manually or clean up the branch; Factory Lab makes no further writes to the original repository.

### Delivery guards

- Refuse delivery if the execution is not in `completed` status.
- Refuse delivery if the original repository working tree is dirty.
- Refuse delivery if the destination feature branch already exists.
- Refuse delivery if out-of-scope changes (`scope_violations`) are detected.
- Never stage ignored files, unrelated changes, or known secrets accidentally.
- Do not modify the original repository before explicit delivery confirmation.
- Never automatically merge into the original branch; user decides whether to merge or open a PR manually.
- No GitHub PR creation in M5.

---

## 17. Worktree cleanup and artifact retention

### `factory task cleanup <exec-id>`

- `--force` may remove a paused execution's worktree working directory when no OpenCode subprocess is active, explicitly discarding its uncommitted work.
- `--force` must **never** permit deleting a worktree belonging to an active/running execution (one with a live OpenCode subprocess).
- A paused execution has no running OpenCode subprocess under the M5 model, but it is still non-terminal; `cleanup` without `--force` refuses for paused executions.
- Worktree cleanup must never delete execution records, approval decisions, logs, artifacts, or test results. These survive all worktree cleanup.
- Artifact deletion remains a separate deferred capability.
- Removes the Git worktree working directory only.

### Retention

- Worktrees retained until explicit delivery acknowledgment or cleanup.
- Execution sidecars, approval decisions, logs, artifacts, and test results retained indefinitely until explicitly removed.
- No automatic retention cleanup in M5.

---

## 18. Concurrency behavior and documented limitations

### Concurrent tasks

- Multiple execution attempts may run simultaneously against the same registered project.
- Each attempt gets its own adjacent worktree and `ExecutionRecord`.
- **Deterministic latest-attempt selection:** When attempts are created concurrently, `factory task status` selects the latest attempt by a deterministic ordering: highest `attempt_number`, then most recent `created_at`, then `exec_id` as final tiebreaker. `list_for_task` returns all attempts sorted by `created_at` descending with the same tiebreakers.
- No project-level locking in M5.
- Shared-resource conflicts (e.g., installed dependencies, port conflicts) and delivery branch conflicts are documented as limitations, not prevented.

---

## 19. Cross-check against existing documentation

| Existing principle | M5 alignment |
|-------------------|--------------|
| Control plane vs execution plane separation (ADR-003) | Execution plane invoked only through `CodingRuntime`/`ExecutionEnvironment` interfaces |
| Runtime/provider independence (ADR-005) | OpenCode adapter behind `CodingRuntime`; no OpenCode imports in control plane |
| Local-first/cloud-capable (ADR-001) | Local process execution; `ExecutionEnvironment` interface preserves cloud path |
| CLI-first (ADR-002) | CLI commands are thin presentation layer delegating to `ExecutionService` |
| Modular monolith (ADR-004) | New `execution/` package; no new service boundaries |
| Security model | Secrets allowlisted and redacted; no secrets logged; approval gates enforced outside runtime prompt; prompt instructions not a security boundary |
| System boundaries | Execution in scope for M5; OS sandboxing, resume, database, cloud workers out of scope |

### Required updates

- `ARCHITECTURE.md`: Add execution plane components to the component responsibilities table; clarify Phase 1 (M1–M5) includes workspaces and Git worktrees.
- `PLANNING.md`: M5 Definition of Done updated to reflect execution plane components.
- `TASK.md`: M5 accepted-direction section added; "Task execution (M5)" removed from out-of-scope.

---

## 20. Edge case resolutions

### Execution status vs task status consistency

| Task status | Execution status during run |
|-------------|----------------------------|
| `approved` | `queued` → `running` → `completed`/`failed`/`paused` |

- Task remains `approved` for the entire execution; execution status is tracked separately in `ExecutionRecord`.
- Execution-level status (`running`, `completed`, etc.) is distinct from step-level status (`ExecutionStepStatus`).
- `ExecutionRecord` references the exact `plan_revision` to prevent ambiguity if the task is replanned.

### Multiple attempts

- Each `ExecutionRecord` is a new attempt with a unique `exec_id` and `attempt_number`.
- All attempts are retained; `factory task status` shows the latest; `factory task executions` lists all.
- Each attempt references its exact plan revision.

### Dirty original working tree

- `deliver` refuses if the original repository working tree is dirty.
- User must clean or commit original repo changes before delivery.

### Existing branch name

- `deliver` refuses if the target feature branch already exists; user must choose an alternate branch name or clean up.

### Uncommitted worktree changes on cleanup

- `cleanup` refuses unless `--force` is supplied, protecting failed and uncommitted work.
- `--force` never permits deleting a worktree for an active/running execution.

### Corrupted execution records

- `ExecutionStorage.load()` raises `ExecutionStorageError` for corrupted records.
- `ExecutionStorage.list_all()` raises `ExecutionStorageError` if any record is corrupted; never silently omits.

### Storage failure

- A storage failure must never be represented as a successful state transition.
- Failed persistence does not mutate in-memory state as if the operation succeeded.

---

## 21. M5 Definition of Done

M5 is complete only when all the following acceptance criteria are satisfied.

### 1. Execution domain models and lifecycle

- `ExecutionStatus` enum: `queued`, `running`, `completed`, `failed`, `paused`.
- `ExecutionStepStatus` enum: `queued`, `running`, `completed`, `failed`, `paused`.
- `ExecutionRecord`, `ExecutionStepResult`, `ExecutionResult`, `ApprovalDecision` dataclasses defined with type hints and docstrings.
- `ExecutionRecord` includes `attempt_number`, `subprocess_pid`, `process_started_at`, `process_confirmed_stopped`, `approval_decisions`, `worktree_path`, `worktree_metadata_dir`.
- `ExecutionResult` carries `subprocess_pid`, `process_started_at`, `process_confirmed_stopped` for process observation reported by the adapter to `ExecutionService`.
- `TaskRecord` and `TaskStatus` unchanged; no M4 `TaskStatus` values added.
- Execution lifecycle separate from task lifecycle; execution-level status distinct from step-level status.
- `subprocess_pid`, `process_started_at`, and `process_confirmed_stopped` treated as reconciliation evidence, not conclusive proof.

### 2. Execution persistence

- `ExecutionStorage` protocol with `load`, `save`, `list_all`, `list_for_task`.
- `JsonExecutionStorage` implementing the protocol with atomic writes, schema versioning, and JSON sidecars under `~/.factory-lab/executions/`.
- Per-execution directories with `logs/`, `artifacts/`, `test-results/`.
- Corrupted records produce controlled errors; never silently omitted.
- Failed persistence does not mutate in-memory state.
- A storage failure must never be represented as a successful state transition.
- Partial execution evidence (logs, artifacts, step results) preserved on failure; not silently discarded.
- A failed step result (exit code, redacted output, timestamps, artifact references) is persisted; a failed step is not silently discarded or represented as success.
- Initial running-state persistence: the execution record is persisted in `running` state before OpenCode is launched; if persistence fails, OpenCode is not launched.
- OpenCode-executed-but-subsequent-persistence-fails: recoverable output is preserved and potentially stale execution state is reported to the user.

### 3. CodingRuntime and ExecutionEnvironment

- `CodingRuntime` protocol with `execute_step` returning `ExecutionResult`.
- Process observation contract: adapter owns subprocess management; `ExecutionResult` carries `subprocess_pid`, `process_started_at`, `process_confirmed_stopped`; `ExecutionService` owns persistence of those fields; adapter does not depend on `ExecutionStorage`.
- `ExecutionEnvironment` protocol with `prepare` and `cleanup`.
- `LocalProcessEnvironment` implementing `ExecutionEnvironment` with environment allowlist configurable in Factory Lab configuration.
- Default allowlist includes `PATH`, `HOME`/`USERPROFILE`, `SYSTEMROOT` where applicable, `TEMP`, `TMP`; OpenCode credentials/API keys opted in by variable name.
- No OpenCode imports in control plane.

### 4. OpenCode subprocess adapter

- OpenCode invoked as subprocess CLI with worktree working directory as working directory.
- Adapter owns subprocess management: launches OpenCode, observes PID and start time, reports termination via `ExecutionResult.subprocess_pid`, `process_started_at`, `process_confirmed_stopped`; `ExecutionService` persists those fields.
- Opaque stdout/stderr plus exit code captured.
- Secret redaction applied to captured output (known secret env values, API-key patterns, bearer tokens, authorization headers, credential formats).
- Scope violations detected via diff review against `affected_components`.

### 5. Git worktree management

- One worktree per execution attempt in a deterministic directory adjacent to the registered repository.
- Three distinct paths: worktree working directory, Git internal metadata directory, execution artifact directory; never conflated.
- Path collision handling: existing directory never overwritten or reused; non-colliding name derived or clear error.
- Worktree retained until explicit delivery acknowledgment or cleanup.
- Never auto-merged into original branch.

### 6. Step dispatch and plan validation

- Strictly sequential dispatch of approved implementation steps.
- `depends_on` ordering respected; forward dependencies, self-dependencies, cycles, missing/invalid references rejected before dispatch.
- Empty plan (zero `implementation_steps`) rejected before creating a worktree.
- Step failure halts execution; subsequent steps not dispatched.

### 7. Approval gates

- Pre-dispatch, operation-specific human approval for dependency installs, network commands, destructive Git, writes outside affected components.
- Approval tied to specific execution attempt, operation, and affected resources; persisted in `ExecutionRecord.approval_decisions`.
- Deny-by-default for unanticipated sensitive operations wherever interception is available; no blanket step permission.
- Prompt instructions, approval records, and diff review are not security boundaries; do not prevent operations.
- Runtime enforcement claimed only where a verified capability exists; no invented OpenCode permission capability.
- Where Factory Lab cannot reliably intercept/restrict an operation, the limitation is documented and execution is not represented as securely controlled against it.

### 8. CLI commands

- `factory task run`, `factory task logs`, `factory task executions`, `factory task deliver`, `factory task cleanup`, `factory task reconcile` implemented (reconcile if reliably cross-platform implementable; otherwise documented manual workflow).
- Exit codes 0/1/2 per M4 convention.
- `factory task status`/`show` surface latest execution attempt (deterministic: highest `attempt_number`, then most recent `created_at`, then `exec_id`); `show` includes task and execution details.

### 9. Delivery

- `deliver` follows the 7-step workflow: inspect diff, display summary, confirm, stage+commit in worktree, create feature branch, cherry-pick, stop safely on conflicts.
- `deliver` operates only on executions with execution-level status `completed`.
- Cherry-pick is the accepted delivery mechanism (not patch application).
- Cherry-pick failure recovery: if cherry-pick fails after the destination branch is created, preserve the execution worktree and execution commit; report the original repository's resulting branch state; make no further writes to the original repository.
- Refuses on dirty working tree, existing branch name, or out-of-scope changes.
- Never stages ignored files, unrelated changes, or known secrets.
- User confirms each delivery; no auto-merge or PR.

### 10. Cleanup

- `cleanup` refuses on uncommitted changes or non-terminal execution unless `--force`.
- `--force` may remove a paused execution's worktree when no OpenCode subprocess is active, explicitly discarding its uncommitted work.
- `--force` never permits deleting a worktree for an active/running execution.
- Execution records, approval decisions, logs, artifacts, and test results survive all worktree cleanup.
- Artifacts and execution records retained independently of worktree removal.
- Artifact deletion deferred.

### 11. Failure handling

- OpenCode non-zero exit → `failed`, preserved for inspection.
- Interruption → graceful termination attempt, `failed` with interruption reason.
- No resume of terminated processes.
- Crash leaves execution in `running`; explicit user confirmation before marking uncertain execution failed; PID and process-start metadata treated as reconciliation evidence, not conclusive proof; no PID-reuse inference.

### 12. Architecture, testing, and documentation

- ADR-011 through ADR-016 created and consistent with this spec.
- `ARCHITECTURE.md`, `PLANNING.md`, `TASK.md` updated.
- No `.github/workflows/opencode.yml` modifications.
- Unit tests for execution models, storage, interfaces, adapter (mocked subprocess), worktree manager (mocked Git), scope enforcement, approval gates, allowlist, redaction, dependency validation, crash reconciliation.
- CLI integration tests for all M5 commands using temporary directories.
- No network calls in tests; stub OpenCode and Git subprocesses.
- Tests pass without optional dependencies.
- M4 regression tests continue to pass.

---

## 22. Assumptions and unresolved implementation details

All M5 discovery decisions from ADR-011 through ADR-016 are accepted and represented in this specification. The following are genuinely unresolved technical implementation questions:

1. **Reconcile command feasibility:** Whether `factory task reconcile <exec-id>` can be implemented reliably across Windows and Linux; if not, the manual confirmation workflow and its limitations must be documented.
2. **Scope enforcement granularity:** Whether out-of-scope write detection can be made more deterministic (e.g., file-system monitoring) beyond post-hoc diff review, or whether post-hoc review remains the M5 approach.
3. **Default allowlist completeness:** Whether the default allowlist (`PATH`, `HOME`/`USERPROFILE`, `SYSTEMROOT`, `TEMP`, `TMP`) is sufficient for OpenCode to function across target platforms; additional variables may be needed.
4. **PID-based process confirmation:** Whether cross-platform confirmation that a subprocess has stopped (using PID and process-start metadata) is implementable with sufficient reliability to support the `reconcile` command.

---

## Validation summary

- All six M5 ADRs (ADR-011 through ADR-016) are represented in this specification.
- M4 `TaskStatus` and `TaskRecord` are preserved unchanged; execution lifecycle is separate.
- All previously unresolved items from discovery are now recorded as accepted decisions (delivery commit model, environment allowlist, redaction, historical execution listing, crash reconciliation, worktree location).
- Requirements are specific enough to become implementation tickets and tests.
- Security limitations (no OS sandboxing, detective-not-preventive scope enforcement, no resume, prompt instructions not a security boundary) are explicitly documented.
- Deferred capabilities (database, cloud workers, GitHub PR, OS sandboxing, QA step, resume, artifact deletion) are clearly marked out of scope.
- Only `SPEC-M5.md` was modified in this revision; no source, tests, dependencies, ADRs, other documentation, or GitHub workflows were changed.

Stop after revising the specification. Wait for approval before running `/to-tickets`.
