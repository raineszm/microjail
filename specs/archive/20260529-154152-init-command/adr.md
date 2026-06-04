# ADR: `microjail init` environment creation

Date: 2026-05-29
Status: Accepted

## Context

`microjail` needed a reproducible entry point for creating a Workshop/LXD environment from a workspace, with optional local inference and agent configuration.

## Decision

- Expose `microjail init <name> [--inference llama-cpp] [--agent opencode]` as the environment creation command.
- Keep config generation pure and isolated in `microjail.config.*` modules.
- Persist environment metadata in `.microjail/state.json` via `EnvironmentState`.
- Write all local files before invoking Workshop so a failed create cannot leave a remote environment without matching local state.
- Use a thin `microjail.workshop.client` subprocess wrapper for Workshop/LXD CLI calls instead of a broad SDK abstraction.
- Verify the environment exists after creation; do not infer success from a zero exit alone.

## Consequences

- Command orchestration lives in `microjail.commands.init`; YAML/JSON content remains unit-testable without subprocesses.
- One workspace maps to one environment state file.
- Errors fail before mutation where possible, and name the missing prerequisite or failed operation.
