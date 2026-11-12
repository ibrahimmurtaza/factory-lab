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

## Out of scope (future milestones)

- Task intake and execution (M4–M5).
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
