# factory-lab

Autonomous AI-powered software engineering factory.

## Installation

```bash
pip install -e .
```

Requires Python 3.11+. Installs the `factory` console script and the `typer` dependency.

## Configuration

Factory Lab stores its configuration in a local JSON file:

- `~/.factory-lab/config.json` (user home directory on Windows)

The file is created on first `factory init` and updated atomically on each change. No database is used.

## CLI Usage

```text
factory init
factory project add <path>
factory project list
factory project inspect <project-id>
```

### `factory init`

Initialize the local Factory Lab configuration directory. Safe to run repeatedly; an existing configuration is left untouched.

### `factory project add <path>`

Register a local software project. The path must exist and be a directory. Duplicate registrations (by canonical path) are rejected.

Example:

```bash
factory project add .
factory project add C:\Users\you\my-repo
```

### `factory project list`

List all registered projects, showing identifier, name, and repository path.

### `factory project inspect <project-id>`

Inspect a registered project's repository and report its technology stack. The repository is read only; nothing is modified or executed.

The report shows detected languages, frameworks, and infrastructure/tooling (each with supporting evidence), repository structure, and Git metadata where available.

Example:

```bash
factory project inspect <project-id>
```

## Task Management

Factory Lab manages task intake, lifecycle, deterministic planning, and human plan approval:

```text
factory task create <project-id> "<description>"
factory task list
factory task status <task-id>
factory task show <task-id>
factory task plan <task-id>
factory task approve <task-id>
factory task reject <task-id> "<reason>"
factory task cancel <task-id>
```

### `factory task create <project-id> "<description>"`

Register a task in `created` state, tied to a registered project. The task id is globally unique with the `task_` prefix.

### `factory task list`

List all persisted task records.

### `factory task status <task-id>`

Print a concise overview of a task: id, project, description, status, and current revision.

### `factory task show <task-id>`

Print the complete task record: all plan revisions, approval decisions with actor and timestamp, and lifecycle history.

### `factory task plan <task-id>`

Generate a deterministic implementation plan via the control-plane planner and transition the task to `awaiting_approval`. Requires a registered project; missing projects or planning failures produce a clear error and preserve prior state.

### `factory task approve <task-id>`

Approve the current plan revision and transition the task to `approved`. Records the resolved actor and timestamp.

### `factory task reject <task-id> "<reason>"`

Reject the current plan revision with a reason and transition the task to `rejected`. Records the resolved actor and timestamp.

### `factory task cancel <task-id>`

Cancel the task when the current lifecycle state permits (`created`, `awaiting_approval`, `approved`, `rejected`). Cancellation is terminal; `planning` and `cancelled` states cannot be cancelled.

Plan approval does not execute code, modify repositories, or trigger Git operations. Execution is deferred to a future milestone.

## Project Intelligence

Factory Lab inspects registered repositories to detect:

- **Languages:** Python, JavaScript, TypeScript, Java, C#, Go, Rust, PHP, Ruby, Swift, Kotlin, Dart, C, C++
- **Frameworks:** FastAPI, Django, Flask, React, Next.js, Vue, Angular, Svelte, Express, NestJS, Spring Boot, ASP.NET Core, Laravel, Rails, Flutter
- **Infrastructure & tooling:** Docker, Docker Compose, Kubernetes, Terraform, GitHub Actions, GitLab CI, Supabase, PostgreSQL, Redis

Detections are evidence-based: each is backed by observable manifest files or dependency declarations. Unknown technologies are reported without failing inspection.

## Development

Run the test suite:

```bash
python -m pytest
```

See `ARCHITECTURE.md`, `PLANNING.md`, `AGENTS.md`, and `docs/adr/` for the architectural foundation.
