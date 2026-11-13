# PLANNING.md — Development Plan

## Development Phases

| Phase | Goal | Primary deliverable |
|---|---|---|
| Phase 1 — Foundation | Docs, CLI scaffold, project registration, inspection | `ARCHITECTURE.md`, `PLANNING.md`, `TASK.md`, `AGENTS.md`, ADRs, CLI command skeleton |
| Phase 2 — Project & Repo | Register projects, detect tech stack, inspect repos | Project config model, repo inspection, tech detection |
| Phase 3 — Task & Plan | Task intake, implementation planning, plan artifacts | Task model, planner agent, plan representation |
| Phase 4 — Execution | OpenCode adapter, run task, status/logs | Coding runtime adapter, task runner, status tracking |
| Phase 5 — Quality & Approval | QA, validation, approval gates | QA review step, approval prompts |
| Phase 6 — Persistence & Observability | Durable state, logging, history | Application DB, OpenTelemetry tracing |

## Milestones and Dependencies

```
M1: Architectural foundation (docs)        -> no code dependencies
M2: CLI scaffold (init, project add/list)  -> M1, Typer decision
M3: Project registration & inspection      -> M2, Git CLI
M4: Task intake & planning                 -> M3
M5: OpenCode execution & tracking          -> M4, OpenCode adapter
M6: QA & approval gates                    -> M5
M7: Persistence & observability            -> M6, DB/OTel decision
```

Dependencies:
- M2 requires CLI framework selection (Typer recommended, not yet installed).
- M5 requires M4 and OpenCode available in execution environment.
- M7 requires infrastructure decision (PostgreSQL/Redis) — deferred past Phase 1.

## Definition of Done

### M1 — Architectural foundation
- `ARCHITECTURE.md`, `PLANNING.md`, `TASK.md`, `AGENTS.md` exist and are consistent.
- `docs/adr/ADR-001` through `ADR-005` exist with context/decision/alternatives/consequences/status.
- No application code or dependencies added.

### M2 — CLI scaffold
- `factory init`, `factory project add <path>`, `factory project list` run without error.
- Commands parse args and print help.
- No project persistence required yet (stub acceptable, marked as such).

### M3 — Project registration & inspection
- Project registered with independent config (repo path, instructions, tech stack, execution settings).
- `factory project inspect <project>` reports repo and detected technology stack.
- Tech detection heuristic documented; no false hard dependencies on specific languages.

### M4 — Task intake & planning
- `factory task create <project> "<description>"` creates a task in `created` state.
- `factory task plan <task-id>` generates a deterministic implementation plan; plan enters `awaiting_approval`.
- `factory task approve` / `factory task reject` / `factory task cancel <task-id>` record the actor-attributed approval decision; plan approval is part of Phase 1.
- `factory task status` / `factory task show <task-id>` return concise task state and the full record.
- Plan approval does not execute code or modify repositories (execution deferred to M5).

### M5 — OpenCode execution & tracking
- OpenCode adapter executes the plan against the registered project.
- `factory task logs <task-id>` returns execution output.
- Task status reflects running/completed/failed.

### M6 — QA & approval gates
- QA/review step runs tests/lint after implementation.
- Approval gate prompts before sensitive operations (file writes outside workspace, destructive Git).

### M7 — Persistence & observability
- Task and project state persisted (database decision required).
- Execution traces emitted (OpenTelemetry decision required).

## Risks and Technical Prerequisites

| Risk | Mitigation |
|---|---|
| OpenCode adapter coupling | Keep adapter behind interface; no direct OpenCode imports in orchestration |
| Model provider lock-in | Provider abstraction before any model call in orchestration |
| Premature infrastructure | No DB/Docker/Redis until M7; use local files in Phase 1–5 |
| GitHub dependence | GitHub API treated as optional integration; Git CLI is the default |
| Over-abstraction | Only add interfaces when a second implementation is plausible |

Prerequisites before M2: Python available, Typer decision confirmed (not installed), OpenCode accessible in execution environment.
