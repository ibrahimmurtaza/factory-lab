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
