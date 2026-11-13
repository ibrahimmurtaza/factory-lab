# TASK.md — Actionable Engineering Tasks (M2, M3)

## Status

**M2 (CLI scaffold): Completed.** Initial CLI implemented, tested, and validated.
**M3 (Project intelligence): Completed.** Repository inspection and technology detection implemented, tested, and validated.

## M2 — Initial CLI (completed)

**Task:** Scaffold the Factory Lab CLI command structure and project registration command.

Implemented `factory init`, `factory project add <path>`, and `factory project list` so a user can initialize Factory Lab and register a local software project.

### Acceptance Criteria (all met)

1. `factory --help` prints available commands including `init` and `project`.
2. `factory init` creates a local Factory Lab config directory and exits 0.
3. `factory project add <valid-path>` registers the project and exits 0.
4. `factory project add <invalid-path>` returns a non-zero exit code and a clear error message.
5. `factory project list` lists registered projects.
6. No new runtime dependencies installed beyond what was already available (typer 0.26.8 pre-installed).
7. Existing `.github/workflows/opencode.yml` is not modified.
8. Code follows AGENTS.md (type hints, docstrings, error messages, exit codes).

## M3 — Project Intelligence (completed)

**Task:** Inspect a registered software repository, identify its structure and technology stack, and present a structured project profile.

Implemented `factory project inspect <project-id>` plus a read-only repository inspection component and an evidence-based technology detection system.

### Implemented CLI command

- `factory project inspect <project-id>` — finds the registered project, validates its repository still exists, inspects it read-only, detects its tech stack, identifies important files/directories, detects Git metadata, and displays a structured report. Unknown project IDs and missing repository paths produce useful errors.

### Configuration storage

- Local JSON file at `~/.factory-lab/config.json` (user home directory on Windows). No database.

### Supported detection categories

**Languages:** Python, JavaScript, TypeScript, Java, C#, Go, Rust, PHP, Ruby, Swift, Kotlin, Dart, C, C++

**Frameworks:** FastAPI, Django, Flask, React, Next.js, Vue, Angular, Svelte, Express, NestJS, Spring Boot, ASP.NET Core, Laravel, Rails, Flutter

**Infrastructure & tooling:** Docker, Docker Compose, Kubernetes, Terraform, GitHub Actions, GitLab CI, Supabase, PostgreSQL, Redis

### Detection evidence strategy

Each detection records its category (`language`, `framework`, or `infrastructure`) and supporting evidence strings (e.g. `pyproject.toml declares fastapi`, `package.json depends on react`). Languages are distinguished from frameworks and infrastructure; a framework is only claimed when identifiable manifest/dependency evidence exists. Multiple languages and monorepo-like structures are supported. Unknown technologies do not cause failures.

### Security safeguards

- Repository contents are treated as untrusted input; nothing is executed or installed.
- No network requests, no arbitrary shell commands.
- Symlinks escaping the repository root are not followed.
- Generated/large directories (`.git`, `node_modules`, `.venv`, `venv`, `__pycache__`, `dist`, `build`, `.next`, `target`, `vendor`) are excluded from traversal.
- Unreadable/malformed manifests are handled gracefully.
- No secrets are printed.
- Inspected repositories are never modified.

## M4 — Task Intake and Planning (completed)

**Task:** Implement task intake, lifecycle management, deterministic implementation planning, and human plan approval via the CLI.

Implemented `factory task` commands plus the `TaskService`, `TaskStorage`, `DeterministicTaskPlanner`, and `ActorResolver` components in the control plane.

### Implemented CLI commands

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

`factory task run` is reserved for a future execution-capable milestone and is not introduced in M4.

### Data model

Task lifecycle states: `created`, `planning`, `awaiting_approval`, `approved`, `rejected`, `cancelled`. A `TaskRecord` holds the task id, project id, description, status, timestamps, current revision, plan revisions, and lifecycle history. Plan revisions are sequential integers starting at 1; each wraps an `ImplementationPlan` with objectives, steps, components, dependencies, acceptance criteria, testing strategy, risks, and evidence. Approval belongs to an individual `PlanRevision`; historical approvals are preserved when a revision is superseded.

### Persistence

Task state is persisted as one JSON sidecar file per task under `~/.factory-lab/tasks/<task-id>.json`, with atomic writes (temporary file + `os.replace`) and schema versioning. A `TaskStorage` protocol (`load`, `save`, `list_all`) is implemented by `JsonTaskStorage` and is replaceable by a database at M7.

### Lifecycle and approval

Valid transitions: `created` → `planning` → `awaiting_approval` → `approved` or `rejected`; `rejected` → replan → `awaiting_approval`; `awaiting_approval` → `cancelled`; `approved` → replan → `awaiting_approval` (previous approved revision becomes `superseded`, retaining its `ApprovalRecord`). `cancelled` is terminal. Cancellation is permitted in `created`, `awaiting_approval`, `approved`, and `rejected`; disallowed in `planning` and `cancelled`. Actor attribution is resolved internally via `ActorResolver` (`FACTORY_LAB_ACTOR` env var, then `getpass.getuser()` fallback) and recorded on approval/rejection/cancellation.

### Planning

`DeterministicTaskPlanner` produces a fully populated `ImplementationPlan` from a task description and M3 `ProjectProfile`. It uses a generic six-step implementation lifecycle plus evidence-based technology overlays (Python, FastAPI, Django, React, Next.js, Flutter, Docker, PostgreSQL) gated on project evidence. No file paths, package names, versions, or test commands are invented. Same inputs produce equivalent plan output.

### Acceptance Criteria (all met)

1. `factory task create` creates a task in `created` state with a globally unique `task_`-prefixed id.
2. All eight task commands registered under `factory task`; exit codes 0 (success), 1 (`FactoryError`), 2 (Typer arg validation).
3. Valid lifecycle transitions enforced; invalid transitions raise `InvalidTaskTransitionError`.
4. Rejection and cancellation record reasons; cancellation is terminal.
5. Replanning after rejection appends a new revision; historical revisions and approvals preserved.
6. `status` provides a concise overview; `show` displays the complete record and revision history.
7. Plan approval does not execute code, modify repositories, or trigger Git operations (execution deferred to M5).
8. No `ModelProvider`, OpenRouter integration, API-key handling, network, database, Docker, or cloud infrastructure in M4.

### Validation Results

- 237 automated tests pass (M2/M3 regression + M4 new), 1 skipped (symlink test on Windows).
- Manual validation: all eight `factory task` commands behave as specified across exit codes 0/1/2.
- `.github/workflows/opencode.yml` remains untouched.

## Out of scope (future milestones)

- Task execution (M5).
- Persistence to a database (M7).
- Web dashboard, API, Docker, cloud infrastructure.

## Implementation Dependencies

- Python 3.14.5 runtime.
- CLI framework: Typer 0.26.8 (approved; already present in environment).
- Standard library for config file I/O and detection (`json`, `tomllib`, `pathlib`, `tempfile`, `uuid`).

## Validation Results

- 46 automated tests pass (M2 regression: `tests/test_cli.py`, `tests/test_projects.py`, `tests/test_config.py`; M3: `tests/intelligence/test_inspector.py`, `tests/intelligence/test_detection.py`, `tests/test_cli_inspect.py`), 1 skipped (symlink test on Windows).
- Manual validation: `factory --help`, `factory init` (first + repeated), `factory project add` (valid / invalid / duplicate), `factory project list`, and `factory project inspect` (Python, JavaScript, infrastructure, Git metadata cases) all behave as specified.
- Inspection verified against a real local project (`factory-lab` itself); repository left unmodified.
- Configuration persists across separate CLI invocations.
- `.github/workflows/opencode.yml` remains untouched.

## Notes

- Do not add databases, Docker, or cloud infrastructure.
- Do not modify GitHub Actions workflows.
