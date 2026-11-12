# AGENTS.md — Factory Lab Agent Instructions

## Coding Standards

- Language: Python 3.
- Style: PEP 8, 100-char line limit, double quotes.
- Type hints required on all public functions and module-level APIs.
- Docstrings on public modules, classes, and functions (Google style).
- No comments unless explaining non-obvious rationale (per codebase convention).
- Error messages must be user-facing and actionable.
- Exit codes: 0 success, non-zero failure with stderr message.

## Architecture Constraints

- **Control plane vs execution plane:** Orchestration logic never imports execution-plane internals directly; communication via interfaces only.
- **Runtime independence:** OpenCode is an adapter behind a `CodingRuntime` interface. No OpenCode imports in orchestration or project management.
- **Provider independence:** Model providers behind a `ModelProvider` interface. OpenRouter is one implementation.
- **No premature abstractions:** Only add an interface when a second implementation is concrete or clearly planned.
- **No premature infrastructure:** No databases, Docker, Redis, or cloud SDKs until Phase 6 (M7).
- **GitHub is optional:** GitHub API integration is additive; Git CLI is the default repository operation.
- **Modular monolith:** Single codebase with clear package boundaries; no microservices.

## File Organization Principles

```
factory-lab/
  ARCHITECTURE.md
  PLANNING.md
  TASK.md
  AGENTS.md
  README.md
  docs/
    adr/
      ADR-001.md ... ADR-005.md
  src/
    factory/
      __init__.py
      cli.py            # Typer/argparse command definitions
      control/
        project.py      # Project registration & config
        task.py         # Task intake & lifecycle
        orchestration.py# Agent orchestration
        planner.py      # Architect agent: planning
        runtime.py      # CodingRuntime interface
        provider.py     # ModelProvider interface
      execution/
        adapter_opencode.py  # OpenCode adapter
        environment.py # Execution environment abstraction
        git.py         # Git CLI wrapper
      config.py        # App config (paths, secrets from env)
      errors.py        # Domain errors
  tests/
    unit/
    integration/
  pyproject.toml       # when packaging is added
```

- One responsibility per module.
- Tests mirror `src/` structure under `tests/`.
- No `docs/` content beyond `docs/adr/` unless explicitly required.

## Testing Expectations

- Unit tests for every public function; mock adapters and external processes.
- Integration tests for CLI command end-to-end flows using temporary directories.
- No network calls in tests; stub OpenRouter/OpenCode.
- Run `pytest` from repo root; aim for 100% coverage of control-plane logic.
- Tests must pass without installing optional dependencies.

## Documentation Requirements

- Every user-facing CLI command documented in `TASK.md` or milestone docs.
- Every architectural decision recorded in `docs/adr/ADR-NNN.md`.
- ADR format: Context, Decision, Alternatives, Consequences, Status.
- Keep documents concise; avoid duplicating code behavior in prose.

## Security Rules

- Secrets read from environment variables only; never hardcoded or logged.
- All file operations scoped to the registered project workspace.
- Approval gate required before: writes outside workspace, destructive Git ops, code delivery.
- Audit every approved/rejected action (timestamp, actor, action).
- No credentials committed to the repository.

## Instructions for Future Coding Agents

1. Read `ARCHITECTURE.md`, `PLANNING.md`, `AGENTS.md`, and relevant ADRs before writing code.
2. Confirm technology choices (Typer, PostgreSQL, etc.) are approved before adding dependencies.
3. Do not implement functionality beyond the current milestone without approval.
4. Do not modify `.github/workflows/` files.
5. Do not commit, push, or create branches unless explicitly asked.
6. Run lint + typecheck + tests after every change.
7. Update ADRs when a decision changes; mark superseded ADRs with `Status: superseded`.
