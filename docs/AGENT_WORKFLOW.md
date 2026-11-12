# Factory Lab Agent Workflow

This document describes the Factory Lab autonomous development workflow, in which GitHub Issues drive development tasks and the OpenCode agent implements them under human supervision.

## 1. Defining tasks with GitHub Issues

Development work is scoped and tracked through GitHub Issues. Each issue describes a single, well-scoped development task: the goal, required behavior, acceptance criteria, and any relevant context. Issues are the single source of truth for what the agent should implement.

## 2. How OpenCode implements tasks

OpenCode is invoked through the `Factory Lab - OpenCode Agent` GitHub Actions workflow (`.github/workflows/opencode.yml`). The workflow runs when a comment is created on an issue or pull request, and:

- The commenter is a trusted repository contributor (`OWNER`, `MEMBER`, or `COLLABORATOR`), not a bot.
- The comment contains `/oc` or `/opencode`.

When triggered, the agent checks out the repository on `ubuntu-latest`, configures a git identity (`github-actions[bot]`), and runs the OpenCode agent using `anomalyco/opencode/github@latest` with the `openrouter/nvidia/nemotron-3.5-super-vl` model. The agent reads the linked issue, implements the requested changes, and pushes them to a feature branch.

## 3. Isolating changes with feature branches

Every agent implementation is developed on a dedicated feature branch, created from the repository's default branch (`main`). This isolates the agent's changes from the main line of development and keeps the default branch stable until the changes are reviewed and approved.

## 4. Creating pull requests for human review

The OpenCode agent opens a pull request against the default branch (`main`) from its feature branch. The pull request includes:

- A summary of the changes.
- The files modified.
- Validation performed.
- Any limitations or assumptions.

The pull request is the mechanism by which a human reviewer inspects the agent's work before it can be merged.

## 5. Validating implementations with tests and CI

Automated tests and CI checks run to validate that the agent's implementation is correct and does not introduce regressions. The workflow's permissions (`contents: write`, `pull-requests: write`, `issues: write`) allow the agent to create branches and pull requests, but validation of the implementation itself relies on the repository's existing test and check tooling. Existing tests and checks remain unaffected by the agent's changes.

## 6. Requiring human approval before merging

Human approval is required before merging because the agent operates autonomously and its output must be verified by a reviewer. Reviewers confirm that the implementation matches the issue requirements, follows repository conventions, and passes validation. Only after approval is the pull request merged into the default branch.