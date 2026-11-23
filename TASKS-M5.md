# TASKS-M5.md — M5 Implementation Tickets

**Status:** For review (not yet implemented)
**Dependencies:** M1–M4 complete; SPEC-M5 approved; ADR-011 through ADR-016 recorded
**Order:** Tickets must be implemented in dependency order; tests written alongside code
**Do not:** introduce new architectural decisions, reopen settled questions, modify source/tests/ADRs/docs/workflows, commit or push

---

## Ticket M5-01: Execution domain models, exceptions, and persistence layer

**Priority:** High  
**Dependencies:** None  
**Modules:** `src/factory/control/execution_models.py`, `src/factory/control/execution_storage.py`, `src/factory/errors.py`

### Scope

- Define `ExecutionStatus` enum: `queued`, `running`, `completed`, `failed`, `paused`.
- Define `ExecutionStepStatus` enum: `queued`, `running`, `completed`, `failed`, `paused`.
- Define `ApprovalDecision` dataclass: operation, reason, affected_resources, approved, actor, timestamp, execution_attempt.
- Define `ExecutionRecord` dataclass: exec_id, task_id, plan_revision, attempt_number, status, created_at, updated_at, started_at, completed_at, worktree_path, worktree_metadata_dir, branch_name, exit_code, interruption_reason, error_message, subprocess_pid, process_started_at, process_confirmed_stopped, approval_decisions, step_results.
- Define `ExecutionStepResult` dataclass: step_number, status, started_at, completed_at, exit_code, output, artifacts, test_results, scope_violations.
- Define `ExecutionResult` dataclass: step_number, status, exit_code, output, artifacts, test_results, scope_violations, subprocess_pid, process_started_at, process_confirmed_stopped.
- Add exception classes to `src/factory/errors.py`: `ExecutionError`, `ExecutionStorageError`, and related; reuse existing `FactoryError`/`TaskError` hierarchy where applicable.
- Define `ExecutionStorage` protocol: `load`, `save`, `list_all`, `list_for_task`.
- Implement `JsonExecutionStorage`: JSON sidecars under `~/.factory-lab/executions/<exec-id>.json`; atomic writes (tempfile + `os.replace`); `schema_version` field; schema validation on load including rejection of unsupported or unknown `schema_version` values; `list_for_task` sorted by creation time descending; exec ID/filename mismatch checks; corrupted records raise `ExecutionStorageError` and are never silently omitted.
- Persistence failure must never be represented as a successful state transition; failed persistence does not mutate in-memory state.
- `ExecutionRecord` and `TaskRecord` remain separate; M4 `TaskStatus` and `TaskRecord` unchanged.

### Acceptance criteria

- All dataclasses have type hints and Google-style docstrings.
- `ExecutionStatus` and `ExecutionStepStatus` are proper enums with the 5 agreed values (no M4 `TaskStatus` values added).
- `ExecutionResult` carries `subprocess_pid`, `process_started_at`, `process_confirmed_stopped` for process observation.
- `save` then `load` round-trips an `ExecutionRecord` correctly.
- `list_for_task` returns executions for a task sorted newest first.
- Atomic write via tempfile + `os.replace`.
- Persisted record contains `schema_version`.
- Unsupported or unknown `schema_version` raises `ExecutionStorageError` on `load`.
- Stored exec ID matches filename; mismatches raise `ExecutionStorageError`.
- Corrupted JSON raises `ExecutionStorageError` on `load`; `list_all` raises if any record is corrupted.
- Missing file returns `None` from `load`.
- Temporary files cleaned up after write failures.
- M4 `TaskRecord`, `TaskStatus`, and task-planning behavior unchanged.

### Tests

- Unit tests for all model constructors and field defaults.
- Unit tests for exception hierarchy and chaining.
- Unit tests for save/load round-trip, list_all, list_for_task, atomic write, corrupted file handling, missing file.
- Use temporary directories; no dependence on `~/.factory-lab` in tests.
- No network, no external processes.

---

## Ticket M5-02: CodingRuntime and ExecutionEnvironment interfaces

**Priority:** High  
**Dependencies:** M5-01  
**Modules:** `src/factory/control/runtime.py`, `src/factory/control/environment.py`

### Scope

- Define `CodingRuntime` protocol: `execute_step(step, plan, worktree_path, environment, observe=None) -> ExecutionResult`. The optional `observe` callback receives `(subprocess_pid: int | None, process_started_at: datetime | None, process_confirmed_stopped: bool | None)` and is invoked by the adapter when the subprocess starts (PID + start time) and when it terminates (confirmed stop).
- Define `ExecutionEnvironment` protocol: `prepare(worktree_path) -> dict[str, str]`, `cleanup(worktree_path) -> None`.
- Protocols have no dependencies on `ExecutionStorage` or CLI components.
- No implementations in this ticket; interface definitions only.
- No OpenCode-specific types or imports in the control plane.
- `CodingRuntime.execute_step` is the single entry point; process observation is reported through the `observe` callback plus the returned `ExecutionResult`.

### Acceptance criteria

- `CodingRuntime.execute_step` signature matches the protocol exactly, including the optional `observe` callback parameter.
- `ExecutionEnvironment.prepare` returns an allowlisted environment dictionary; `cleanup` releases environment resources.
- Protocols are importable and usable without instantiating any adapter or environment implementation.
- Control plane depends only on the interfaces, not on OpenCode internals.
- The `observe` callback is invoked by adapters at subprocess start (PID + start time) and termination (confirmation); it carries no `ExecutionStorage` dependency.

### Tests

- Unit tests verifying protocol signatures (including the optional `observe` callback parameter) and that no execution-plane imports leak into control plane modules.
- Verify the `observe` callback parameter type matches the protocol (`Callable[[int | None, datetime | None, bool | None], None] | None`).
- No network, no external processes.

---

## Ticket M5-03: LocalProcessEnvironment and environment allowlist

**Priority:** High  
**Dependencies:** M5-02  
**Module:** `src/factory/execution/environment.py`

### Scope

- Implement `LocalProcessEnvironment` implementing `ExecutionEnvironment`.
- `prepare` returns an allowlisted subset of environment variables for subprocess execution.
- Allowlist is configurable in Factory Lab configuration.
- When existing Factory Lab configuration lacks the new execution configuration section, use backward-compatible defaults (platform essentials only; no credentials).
- Default allowlist includes essential platform variables: `PATH`, `HOME`/`USERPROFILE`, `SYSTEMROOT` where applicable, `TEMP` and `TMP`.
- OpenCode credentials and provider API keys must be explicitly opted in by variable name.
- Never persist secret values.
- Does not inherit the full caller environment.
- `cleanup` releases environment resources associated with a worktree.
- Local process only; no cloud infrastructure.

### Acceptance criteria

- `prepare` returns only allowlisted variables; full caller environment is not inherited.
- Default allowlist includes the required platform variables.
- Missing execution configuration section falls back to safe defaults without error.
- Credentials/API keys are included only when explicitly opted in by name.
- Secret values are never written to logs or persisted.
- No cloud dependencies introduced.

### Tests

- Unit tests for allowlist contents, opt-in behavior for credentials, non-inheritance of full environment, missing-config default fallback.
- Mock environment variables; no real secret dependence.
- No network, no external processes.

---

## Ticket M5-04: Git worktree manager

**Priority:** High  
**Dependencies:** M5-01  
**Module:** `src/factory/execution/git.py`

### Scope

- Implement `WorktreeManager`: create a Git worktree per execution attempt.
- Worktree working directory named `factory-lab-<task-id>-<attempt>`, located in a deterministic directory adjacent to the registered repository (not inside Git's internal `.git/worktrees` metadata directory).
- Worktree checked out from the project's current branch at execution start.
- **Path collision handling:** before creating a worktree working directory, verify no directory with the target name exists; never overwrite or reuse an existing directory; derive a non-colliding name or fail with a clear, actionable error. Collision handling accounts for concurrent execution attempts: if two attempts derive the same worktree name, they must not collide; each derives a unique non-colliding name or fails with a clear error.
- Inspect changed files in the worktree working directory for scope enforcement: added, modified, deleted, renamed, untracked files.
- Normalize repository-relative paths; safely handle path traversal and symlinks.
- Cleanup removes the Git worktree working directory only; never deletes execution records, approval decisions, logs, artifacts, or test results.
- Distinguish three paths: worktree working directory, Git internal worktree metadata directory, execution artifact directory; never conflate them.
- Never modify the original repository branch except through the explicit `deliver` flow.

### Acceptance criteria

- Worktree created in deterministic adjacent location with correct naming.
- Existing directory with the target name is never overwritten or reused.
- Concurrent attempts deriving identical worktree names do not collide; each receives a unique name or a clear error.
- Changed-file inspection accounts for add/modify/delete/rename/untracked.
- Path normalization and symlink/traversal handling safe.
- Worktree removal deletes only the working directory; execution artifacts and records preserved.
- Three path categories kept distinct in implementation and tests.

### Tests

- Unit tests for worktree creation, naming, collision handling, changed-file inspection, path normalization, cleanup behavior.
- Mock Git subprocess; no real repository mutation in unit tests.
- No network, no external processes.

---

## Ticket M5-05: OpenCode subprocess adapter

**Priority:** High  
**Dependencies:** M5-02, M5-03, M5-04  
**Module:** `src/factory/execution/adapter_opencode.py`

### Scope

- Implement `OpenCodeAdapter` implementing `CodingRuntime`.
- Invoke OpenCode as a subprocess CLI, passing the approved step description and plan context via stdin/args.
- Set the subprocess working directory to the execution worktree working directory.
- Use the allowlisted environment from `ExecutionEnvironment.prepare`.
- Own subprocess management: launch OpenCode; observe and report the subprocess PID and start time **while the process is running** through the `observe` callback; report termination (`process_confirmed_stopped`) through the `observe` callback when the OpenCode subprocess exits.
- Report subprocess-start information (PID, start time) via the `observe` callback while the OpenCode subprocess is running.
- Report termination information (`process_confirmed_stopped`) via the `observe` callback when the OpenCode subprocess exits.
- Preserve `ExecutionResult` as the final step result, carrying `subprocess_pid`, `process_started_at`, and `process_confirmed_stopped`.
- The adapter must not depend on `ExecutionStorage` or call persistence directly; observations are delivered only through the `observe` callback and `ExecutionResult`.
- Treat PID and process-start metadata as reconciliation evidence, not proof that a process is alive or dead.
- Capture stdout and stderr as opaque text, combined into a single `output` field, plus exit code; do not rely on an unconfirmed OpenCode structured event protocol.
- Redact known secret environment-variable values, common API-key patterns, bearer tokens, authorization headers, and identifiable credential formats **before** captured output enters any persisted execution record or log file.
- Never write environment values or secrets to execution logs.
- Detect scope violations by comparing changed files in the worktree against `affected_components` paths (post-hoc diff review, not prevention).
- Return a structured `ExecutionResult` built from exit code, output, discovered artifacts, test results, scope violations, and process observation fields.
- Never import OpenCode-specific types or libraries into the control plane.
- Treat OpenCode output as observability, not as a security enforcement mechanism.

### Acceptance criteria

- OpenCode invoked as subprocess CLI with worktree as working directory and allowlisted environment.
- Adapter invokes `observe` callback with PID and start time while the OpenCode subprocess is running.
- Adapter invokes `observe` callback with termination confirmation when the OpenCode subprocess exits.
- `ExecutionResult` includes PID, start time, and termination confirmation fields.
- Output captured as opaque text (stdout and stderr combined); secret values redacted before persistence.
- Scope violations detected via diff review against `affected_components`.
- No OpenCode imports present in control plane modules.
- Adapter does not depend on `ExecutionStorage`; no persistence calls in the adapter.
- PID/process-start metadata treated as reconciliation evidence, not proof of process liveness.

### Tests

- Unit tests for adapter behavior with mocked subprocess (capture output, exit code, PID recording, redaction, scope violation detection).
- Verify `observe` callback receives PID and start time while the mocked subprocess is running, and termination confirmation when it exits.
- Verify process metadata is available before the subprocess terminates (crash reconciliation scenario).
- Verify no OpenCode-specific imports in control plane.
- No network, no real OpenCode subprocess in unit tests.

---

## Ticket M5-06: ExecutionService — orchestration and sequential step dispatch

**Priority:** High  
**Dependencies:** M5-01, M5-02, M5-04, M5-05, M5-07  
**Module:** `src/factory/control/execution.py`

### Scope

- `ExecutionService` owns the complete execution workflow: execution record creation and persistence, plan validation, worktree lifecycle coordination, sequential step dispatch, execution and step status transitions, approval checkpoint coordination, result persistence, failure handling, and delivery business logic.
- Create `ExecutionRecord` in `queued` state linked to a task and the exact approved plan revision.
- Validate the plan before dispatch: reject empty plan (zero `implementation_steps`); reject `depends_on` with missing dependency, self-dependency, forward dependency, or cycle. Invalid plans are rejected before dispatch; no worktree created, no OpenCode subprocess launched.
- Coordinate worktree creation via `WorktreeManager` (M5-04).
- Receive process observations (subprocess PID, start time, termination confirmation) from the adapter via the `observe` callback and persist them in `ExecutionRecord.subprocess_pid`, `process_started_at`, `process_confirmed_stopped`.
- Persist process metadata (`subprocess_pid`, `process_started_at`) before the OpenCode subprocess terminates so it remains available for crash reconciliation if Factory Lab crashes while OpenCode is running; persist `process_confirmed_stopped` at termination.
- If persisting a process observation (subprocess PID/start time) fails while OpenCode is running, `ExecutionService` must not treat the execution as successfully observed; it reports the persistence failure and applies a documented subprocess handling policy (for example, leave OpenCode running and alert the user that process metadata is unavailable for reconciliation). A running process and a successfully persisted observation are distinct states.
- Persist the execution record in `running` state (with worktree path and branch) before launching OpenCode; if persistence fails, OpenCode is not launched.
- If the worktree is created successfully but persisting the `running` execution record fails, `ExecutionService` does not launch OpenCode, attempts safe cleanup of the newly created worktree, preserves the `queued` execution record, and reports any cleanup failure explicitly rather than silently leaving an orphaned worktree.
- Coordinate pre-dispatch approval checkpoints via M5-07 approval logic before dispatching any step involving a sensitive operation.
- Approval status transitions: execution enters `paused` when awaiting a pre-dispatch approval decision; an approved operation allows the workflow to proceed and execution returns to `running` before dispatch; a rejected operation is not dispatched and follows the failure/rejection behavior specified in SPEC-M5.md. `paused` never means suspending or resuming an already-running OpenCode process.
- Dispatch approved `implementation_steps` strictly sequentially in step-number order, respecting `depends_on` ordering.
- Step status transitions: `queued` → `running` → `completed` (exit code 0) or `failed` (non-zero exit, interruption, error).
- A step awaiting pre-dispatch approval remains `queued` while the execution is `paused`; the execution carries the approval-waiting state, and the step transitions to `running` only when dispatched after approval is granted.
- A step failure halts the entire execution; subsequent steps remain `queued` and are not dispatched.
- Persist each step result (including failed step results with exit code, redacted output, timestamps, artifact references); failed steps are not silently discarded.
- If OpenCode has executed but subsequent persistence fails, preserve recoverable output and report potentially stale execution state to the user.
- A storage failure must never be represented as a successful state transition.
- Execution-level status distinct from step-level status: execution is `running` while any step is `running`; completed only when all steps are `completed`. Execution-level and step-level status lifecycles remain separate.
- Delivery business logic owned by `ExecutionService`: execution eligibility checks (completed status only), original repository cleanliness checks, scope and secret checks, diff inspection and delivery preparation, worktree commit creation, destination branch creation, cherry-pick execution and failure recovery.

### Acceptance criteria

- `ExecutionService` creates an `ExecutionRecord` in `queued` linked to task and plan revision.
- Empty plan rejected before dispatch; no worktree or subprocess created.
- Invalid `depends_on` graphs (missing, self, forward, cycle) rejected before dispatch.
- Worktree lifecycle coordinated via `WorktreeManager`.
- Process observations (PID, start time) persisted to `ExecutionRecord` before the OpenCode subprocess terminates; termination confirmation persisted at exit.
- Process metadata remains available for crash reconciliation after a crash while OpenCode is running.
- Observe-callback persistence failure does not silently succeed; user alerted with a documented subprocess handling policy; the distinction between a running process and a successfully persisted observation is preserved.
- Worktree created but running-state persistence failed: OpenCode not launched; safe worktree cleanup attempted; queued execution record preserved; cleanup failure reported explicitly.
- Steps dispatched strictly sequentially; step N+1 only after step N terminal.
- Pre-dispatch approval checkpoints coordinated before sensitive-operation steps.
- Execution enters `paused` awaiting pre-dispatch approval; returns to `running` on approval before dispatch; rejected operation not dispatched.
- `paused` never implies suspend/resume of a running OpenCode process.
- Step failure halts execution; later steps not dispatched.
- A step awaiting pre-dispatch approval remains `queued` while execution is `paused`; it becomes `running` only when dispatched after approval is granted.
- Recoverable output preserved and reported as potentially stale when result persistence fails.
- Running state persisted before OpenCode launch; failed persistence prevents launch.
- Failed step results persisted with full evidence.
- Storage failure never represented as successful state transition.
- Delivery business logic owned by `ExecutionService`: eligibility, repo cleanliness, scope/secret checks, diff inspection, worktree commit, feature branch creation, cherry-pick execution and recovery.
- Execution-level status distinct from step-level status; lifecycles separate.

### Tests

- Unit tests with mocked `ExecutionStorage`, `CodingRuntime`, `WorktreeManager`, and approval logic.
- Test plan validation rejections (empty plan, missing/self/forward/cycle dependencies).
- Test sequential dispatch and failure halting.
- Test persistence-before-launch and storage-failure behavior.
- Test stale-state reporting when OpenCode output exists but persistence fails.
- Test approval checkpoint coordination before sensitive steps.
- Test process observations (PID, start time) persisted before subprocess termination; termination confirmation persisted at exit.
- Test crash-reconciliation availability of process metadata.
- Test approval status transitions: `queued`→`paused`→`running` on approval; rejected operation not dispatched; `paused` never suspends a running process.
- Test delivery business logic delegated to `ExecutionService` (eligibility, cleanliness, scope/secret, diff, commit, branch, cherry-pick, recovery).
- Test observe-callback persistence failure: OpenCode running but metadata not persisted; user alerted; running-vs-persisted distinction preserved.
- Test worktree created but persistence failed: OpenCode not launched; worktree cleanup attempted; queued record preserved; cleanup failure reported.
- Test recoverable output surfaced when result persistence fails.
- No network, no external processes.

---

## Ticket M5-07: Pre-dispatch approval gates and security limitations

**Priority:** High  
**Dependencies:** M5-01  
**Module:** `src/factory/control/execution.py` (approval logic), tests

### Scope

- Distinguish three approval/enforcement layers:
  1. **Preflight approval:** human approval for identified sensitive operations before dispatch (dependency installation, network-dependent commands, destructive Git operations, file writes outside `affected_components`).
  2. **Runtime enforcement:** restricting the OpenCode subprocess through tool restrictions, OS mechanisms, or other enforceable controls only where a verified capability exists.
  3. **Post-execution detection:** inspecting changed files after each step and recording scope violations via diff review.
- Identify operations for preflight approval using information available in the approved plan (`affected_components`, `dependencies`, implementation step descriptions) and other verified inputs; do not invent OpenCode capabilities.
- Persist `ApprovalDecision` records (operation, reason, affected_resources, approved, actor, timestamp, execution_attempt) in `ExecutionRecord.approval_decisions`.
- Approval tied to a specific execution attempt, operation, and affected resources; applies only to that operation and attempt.
- Deny-by-default for unanticipated sensitive operations wherever interception is available; never silently permitted.
- Do not grant blanket permission for an entire step or execution.
- Prompt instructions, approval records, and post-hoc diff review are **not** security boundaries and do **not** prevent an operation.
- Runtime enforcement claimed only where a verified capability exists; no invented OpenCode permission capability.
- Where Factory Lab cannot reliably intercept or restrict an operation, document the limitation and do not represent execution as securely controlled against that operation.
- Execution-level approval status transitions: execution enters `paused` when awaiting a pre-dispatch approval decision; an approved operation allows the workflow to proceed and execution returns to `running` before dispatch; a rejected operation is not dispatched and follows the failure/rejection behavior specified in SPEC-M5.md. `paused` never means suspending or resuming an already-running OpenCode process.
- A step awaiting pre-dispatch approval remains `queued`; the execution carries the `paused` approval-waiting state. The step transitions to `running` only when dispatched after approval is granted.
- Execution-level and step-level status lifecycles remain separate; `ExecutionStepStatus` values (`queued`, `running`, `completed`, `failed`, `paused`) track step lifecycle independently of execution-level status.

### Acceptance criteria

- Approval decisions persisted per operation, attempt, and affected resources.
- Unanticipated sensitive operations denied where interception available.
- No blanket step-level permission granted.
- Execution enters `paused` awaiting pre-dispatch approval; returns to `running` on approval before dispatch; rejected operation not dispatched (SPEC-M5 failure/rejection behavior).
- `paused` never implies suspend/resume of a running OpenCode process.
- Step remains `queued` while execution is `paused` awaiting approval; execution-level and step-level states tracked separately.
- Execution-level and step-level status lifecycles separate; `ExecutionStepStatus` values (`queued`, `running`, `completed`, `failed`, `paused`) tracked independently.
- Documentation/behavior makes clear that prompt/approval/diff-review are detective, not preventive; runtime enforcement claimed only where verified.
- No OpenCode capabilities invented; unverified capabilities flagged as implementation constraints.
- Limitations documented where interception is not available.

### Tests

- Unit tests for approval capture, persistence, deny-by-default, per-attempt scoping.
- No network, no external processes.

---

## Ticket M5-08: CLI `factory task run` command

**Priority:** High  
**Dependencies:** M5-01, M5-06, M5-07  
**Module:** `src/factory/cli/commands/task.py`

### Scope

- Implement `factory task run <task-id>` as a thin presentation layer.
- Parse arguments; verify task is `approved` via M4 `TaskService`; invoke `ExecutionService` to create an execution, coordinate approvals, and dispatch steps.
- Present approval requests to the user and collect user decisions through an appropriate interaction boundary; pass decisions back to `ExecutionService`.
- Display execution results and errors; return exit codes.
- CLI contains no execution business logic; all workflow owned by `ExecutionService`.
- Exit codes: 0 success, 1 expected `FactoryError`/application failure, 2 Typer argument validation.
- Preserve existing M4 task CLI behavior (create/list/status/show/plan/approve/reject/cancel unchanged).

### Acceptance criteria

- `factory task run <task-id>` exits 0 on successful execution flow; exits 1 on application failure; exits 2 on argument validation failure.
- Verifies task is `approved` before creating execution.
- Delegates all workflow to `ExecutionService`; no business logic in CLI.
- Presents pre-dispatch approvals and collects user decisions.
- Persists execution record and step results via `ExecutionService`.
- M4 task commands remain unchanged and functional.

### Tests

- CLI integration tests using temporary directories for `run` command across success/failure/invalid-argument paths.
- Test CLI helper is monkeypatchable.
- No network; stub OpenCode and Git subprocesses.
- M4 regression tests continue to pass.

---

## Ticket M5-09: CLI `factory task logs` and `factory task executions` commands

**Priority:** Medium  
**Dependencies:** M5-01  
**Module:** `src/factory/cli/commands/task.py`

### Scope

- Implement `factory task logs <task-id>`: return captured execution output for the latest attempt (combined stdout/stderr as stored).
- Implement `factory task executions <task-id>`: distinct command listing all execution attempts for a task (exec ID, status, plan revision, attempt number, timestamps).
- `factory task logs` preserves historical execution output access (latest attempt per SPEC-M5).
- Deterministic latest-attempt selection when attempts created concurrently: highest `attempt_number`, then most recent `created_at`, then `exec_id` as tiebreaker.
- `factory task status <task-id>` surfaces task status plus latest execution attempt status.
- `factory task show <task-id>` includes task and execution details, including approval decisions and step results.
- Exit codes 0/1/2 per M4 convention.
- CLI remains thin; delegates to `ExecutionService`/`ExecutionStorage`.

### Acceptance criteria

- `logs` prints captured output for latest attempt.
- `executions` lists all attempts with required fields.
- Latest attempt selection deterministic under concurrency.
- `status` and `show` surface execution info without altering M4 behavior.
- Exit codes correct.

### Tests

- CLI integration tests for `logs`, `executions`, `status`, `show` with execution records present.
- Test deterministic latest-attempt ordering with concurrent-seeming records.
- No network, no external processes.

---

## Ticket M5-10: Delivery command (`factory task deliver`) via cherry-pick

**Priority:** High  
**Dependencies:** M5-01, M5-04, M5-06  
**Module:** `src/factory/cli/commands/task.py`

### Scope

- Implement `factory task deliver <exec-id>` as a thin presentation layer: parse arguments, invoke `ExecutionService` delivery methods, present diff/summary, collect explicit user confirmation, display results and errors, return exit codes.
- Delivery business logic owned by `ExecutionService` (control/execution.py): execution eligibility checks (completed status only), original repository cleanliness checks, scope and secret checks, diff inspection and delivery preparation, worktree commit creation, destination branch creation, cherry-pick execution and failure recovery.
- CLI contains no delivery business logic; all workflow owned by `ExecutionService`.
- Operates only on executions with execution-level status `completed`.
- Follow the 7-step workflow: inspect worktree diff; display changed files and summary; require explicit user confirmation; stage and commit intended execution changes in the worktree working directory; create a feature branch in the original repository (e.g., `factory-lab/<task-id>/<exec-id>`); cherry-pick the execution commit into that branch; stop safely on cherry-pick conflicts preserving the worktree and execution commit.
- Cherry-pick is the accepted delivery mechanism (patch application not used).
- Refuse delivery if execution not `completed`; if original working tree dirty; if destination branch exists; if out-of-scope changes detected.
- Never stage ignored files, unrelated changes, or known secrets.
- Do not modify the original repository before explicit delivery confirmation.
- Never automatically merge into original branch; user decides merge or PR manually.
- No GitHub PR creation in M5.
- Cherry-pick failure recovery: preserve worktree and execution commit; report original repository's resulting branch state; make no further writes to original repository.

### Acceptance criteria

- `deliver` refuses on non-completed execution, dirty tree, existing branch, out-of-scope changes.
- Delivery follows 7-step workflow with explicit user confirmation.
- Cherry-pick performed into feature branch; conflicts handled safely without further original-repo writes.
- Original repository unmodified before confirmation.
- No auto-merge or PR creation.
- Delivery business logic owned by `ExecutionService`; CLI only invokes service methods, presents diff/summary, collects confirmation, displays results/errors.
- CLI contains no delivery business logic.
- Failed cherry-pick preserves the execution commit and reports the original repository's resulting branch state (for example, branch created but cherry-pick not applied, or partially applied); no further writes to the original repository.

### Tests

- CLI integration tests for `deliver` across guards (not completed, dirty tree, existing branch, out-of-scope) and success path.
- Test cherry-pick conflict recovery preserves worktree and commit.
- Verify delivery business logic resides in `ExecutionService`; CLI is thin presentation layer.
- Use temporary local Git repositories with real Git commands (integration); no real repository mutation.
- No network, no external processes beyond real Git.

---

## Ticket M5-11: Cleanup command (`factory task cleanup`)

**Priority:** Medium  
**Dependencies:** M5-01, M5-04, M5-06  
**Module:** `src/factory/cli/commands/task.py`

### Scope

- Implement `factory task cleanup <exec-id>` as a thin presentation layer: parse arguments, invoke `ExecutionService` cleanup methods, display results and errors, return exit codes.
- Cleanup orchestration owned by `ExecutionService` (control/execution.py); `ExecutionService` delegates worktree working-directory removal to `WorktreeManager` (M5-04).
- Removes the Git worktree working directory only.
- `--force` may remove a paused execution's worktree when no OpenCode subprocess is active, explicitly discarding its uncommitted work.
- `--force` must **never** permit deleting a worktree belonging to an active/running execution (live OpenCode subprocess).
- Uncertain process state (for example, `process_confirmed_stopped` unknown or a live subprocess) never authorizes `--force` deletion of a running execution's worktree; `--force` applies only to paused executions with no active OpenCode subprocess.
- `cleanup` without `--force` refuses on uncommitted changes or non-terminal execution (`running`, `paused`).
- Execution records, approval decisions, logs, artifacts, and test results survive all worktree cleanup.
- Artifact deletion remains a separate deferred capability (not part of M5).
- Exit codes 0/1/2 per M4 convention.
- CLI contains no cleanup business logic; all workflow owned by `ExecutionService`.

### Acceptance criteria

- `cleanup` removes worktree working directory only.
- `--force` removes paused worktree (no subprocess) but never a running worktree.
- Uncertain process state never permits `--force` deletion of a running execution's worktree.
- Without `--force`, refuses on uncommitted changes or non-terminal state.
- Execution records, approvals, logs, artifacts, test results preserved after cleanup.
- Cleanup orchestration owned by `ExecutionService`; CLI is thin presentation layer only.
- Exit codes correct.

### Tests

- CLI integration tests for `cleanup` across force/non-force, paused/running, uncommitted states.
- Verify artifacts and records survive cleanup.
- Use temporary local Git repositories with real Git commands (integration); no real repository mutation.
- No network, no external processes beyond real Git.

---

## Ticket M5-12: Reconcile command and crash recovery

**Priority:** Medium  
**Dependencies:** M5-01, M5-05, M5-06  
**Module:** `src/factory/cli/commands/task.py`, `src/factory/control/execution.py`

### Scope

- Implement `factory task reconcile <exec-id>` if reliable cross-platform implementation is feasible (Windows and Linux); otherwise document the manual confirmation workflow and limitations.
- Treat `subprocess_pid`, `process_started_at`, and `process_confirmed_stopped` as reconciliation evidence, not conclusive proof.
- Never infer a process is dead solely from a potentially reused PID.
- No automatic marking of `running` executions as `failed` solely because a record is still `running` after restart.
- Explicit user confirmation required before marking an uncertain execution `failed`.
- If Factory Lab crashes while OpenCode is running, the OpenCode process may be orphaned; execution record remains in `running`; no automatic reconciliation or process reaping on restart.
- A paused execution has no running OpenCode subprocess under M5 but is still non-terminal.

### Acceptance criteria

- `reconcile` confirms process state and marks uncertain executions failed with explicit user confirmation (if implemented).
- PID-reuse inference never used to declare a process dead.
- No auto-failure transition for uncertain `running` executions after restart.
- Manual reconciliation workflow documented if `reconcile` not cross-platform feasible.

### Tests

- Unit tests for reconciliation logic with mocked process state; PID-reuse scenarios.
- Verify no automatic failure transition without confirmation.
- No network, no external processes.

---

## Ticket M5-13: Integration tests — complete execution and delivery workflows

**Priority:** High  
**Dependencies:** M5-01, M5-02, M5-03, M5-04, M5-05, M5-06, M5-07, M5-08, M5-09, M5-10, M5-11, M5-12  
**Modules:** `tests/control/test_execution.py`, `tests/control/test_execution_storage.py`, `tests/execution/test_adapter_opencode.py`, `tests/execution/test_worktree.py`, `tests/cli/test_task_execution.py`

### Scope

- **Unit tests:** mocked Git and OpenCode subprocesses; verify model, storage, interface, adapter, worktree manager, scope enforcement, approval gates, allowlist, redaction, dependency validation, crash reconciliation logic in isolation.
- **Integration tests:** temporary local Git repositories using real Git commands; verify actual worktree creation/removal, branch creation, staging, committing, cherry-picking, conflict recovery, and preservation of the original repository.
- **End-to-end tests:** complete execution and delivery workflows using temporary repositories and a deterministic test runtime instead of real OpenCode (create task → plan → approve → run → logs/executions/status/show → deliver → cleanup).
- Failure-path tests: OpenCode non-zero exit, interruption, storage failure, stale-state reporting, plan validation rejections, cherry-pick conflict recovery.
- Security tests: allowlist non-inheritance, secret redaction, scope violation detection, deny-by-default unanticipated operations.
- Worktree safety tests: path collision, three-path distinction, cleanup `--force` rules, artifact/record preservation.
- Crash recovery tests: `running` state after restart, PID-reuse non-inference, explicit confirmation before failure marking.
- Concurrency tests: multiple attempts, deterministic latest-attempt selection.
- Regression: run full M2/M3/M4 test suite to confirm no breakage.
- M4 `TaskStatus`, `TaskRecord`, task-planning behavior unchanged.
- Tests pass without optional dependencies; no network calls; stub OpenCode subprocess; real Git only in integration/e2e with temporary repositories.
- Use temporary directories; no dependence on `~/.factory-lab` real path; no mutation of the actual Factory Lab repository.

### Acceptance criteria

- `pytest` from repo root passes all tests (M2/M3/M4 regression + M5 new).
- End-to-end execution and delivery workflow verified.
- Failure-path, security, worktree-safety, crash-recovery, and concurrency tests pass.
- No test depends on real `~/.factory-lab` path; no test makes network calls; no test mutates the actual Factory Lab repository.
- Coverage reported for control-plane execution logic; meaningful gaps documented.

---

## Dependency order

```
M5-01 (models, exceptions, persistence) — independent
M5-02 (runtime/environment interfaces) → M5-01
M5-03 (LocalProcessEnvironment allowlist) → M5-02
M5-04 (Git worktree manager) → M5-01
M5-05 (OpenCode adapter) → M5-02, M5-03, M5-04
M5-07 (approval gates and security) → M5-01
M5-06 (ExecutionService orchestration) → M5-01, M5-02, M5-04, M5-05, M5-07
M5-08 (CLI run) → M5-01, M5-06, M5-07
M5-09 (CLI logs/executions) → M5-01
M5-10 (CLI deliver cherry-pick) → M5-01, M5-04, M5-06
M5-11 (CLI cleanup) → M5-01, M5-04, M5-06
M5-12 (CLI reconcile + crash recovery) → M5-01, M5-05, M5-06
M5-13 (integration tests) → M5-01 through M5-12

DAG: no circular dependencies. M5-01 is the root. M5-02, M5-04, and M5-07 build on M5-01 (M5-03 builds on M5-02; M5-05 builds on M5-02/M5-03/M5-04). M5-07 may proceed independently of M5-02/M5-03/M5-04/M5-05 once M5-01 is done. M5-06 is the central orchestration point and depends on worktree (M5-04), adapter (M5-05), interfaces (M5-02), models (M5-01), and approvals (M5-07), so M5-07 is implemented before M5-06. CLI tickets (M5-08 through M5-12) depend on M5-06 plus their specific direct needs only. M5-10 and M5-11 additionally depend on M5-06 for delivery/cleanup business logic. M5-13 runs last against the full implemented surface.
```

**Review required before implementation begins.** No code should be written until this specification and ticket set is approved.
