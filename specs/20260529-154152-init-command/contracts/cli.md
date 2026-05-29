# CLI Contract: microjail init

**Feature**: `specs/20260529-154152-init-command/`
**Date**: 2026-05-29

This document is the authoritative contract for the `microjail init` command interface.
Implementations MUST conform to this contract. Tests MUST verify it.

---

## Command Signature

```
microjail init <NAME> [--inference BACKEND] [--agent HARNESS] [--force]
```

---

## Arguments

### `NAME` (positional, required)

The name of the Workshop environment to create.

| Property | Value |
|----------|-------|
| Type | String |
| Required | Yes |
| Validation | Non-empty; matches `^[a-zA-Z][a-zA-Z0-9-]*$`; max 63 characters |
| Example | `myproject`, `agent-run-01` |

Error if absent:
```
Error: Missing argument 'NAME'.
```

Error if invalid format:
```
Error: Invalid environment name 'my project'. Names must start with a letter,
contain only letters, digits, and hyphens, and be at most 63 characters.
```

---

## Options

### `--inference BACKEND`

Declare a local inference backend. Determines whether `workshop.yaml` includes the
llama-cpp tunnel configuration.

| Property | Value |
|----------|-------|
| Type | Enum |
| Required | No |
| Supported values (P1) | `llama-cpp` |
| Default | (not set — no inference configured) |

Error if unsupported value:
```
Error: Invalid value for '--inference': 'ollama' is not one of 'llama-cpp'.
```

### `--agent HARNESS`

Declare an AI agent harness to provision. Determines whether `opencode.jsonc` is written.

| Property | Value |
|----------|-------|
| Type | Enum |
| Required | No |
| Supported values (P1) | `opencode` |
| Default | (not set — no agent configured) |

Error if unsupported value:
```
Error: Invalid value for '--agent': 'aider' is not one of 'opencode'.
```

### `--force`

Allow overwriting `workshop.yaml` and `opencode.jsonc` if they already exist.
Without this flag, the command refuses to overwrite existing config files.

| Property | Value |
|----------|-------|
| Type | Flag (boolean) |
| Required | No |
| Default | False |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success: environment created, all files written, state persisted |
| 1 | User error: missing/invalid argument, unsupported value |
| 2 | Precondition failure: prerequisite not installed, existing env/file conflict |
| 3 | Runtime failure: Workshop create failed, verification failed, I/O error |

---

## Output (stdout)

On success, a summary is printed to stdout:

```
Environment 'myproject' created.

  workshop.yaml   → /path/to/workspace/workshop.yaml
  opencode.jsonc  → /path/to/workspace/opencode.jsonc
  state           → /path/to/workspace/.microjail/state.json
```

If `--agent` is not passed, the `opencode.jsonc` line is omitted.
If `--inference` is not passed, the tunnel-related lines are omitted from any summary.

---

## Errors (stderr)

All errors go to stderr. Format: `Error: <message>\n`

| Scenario | Message |
|----------|---------|
| `workshop` not on PATH | `Error: 'workshop' not found. Install Workshop: <URL>` |
| LXD not running | `Error: LXD is not available. Ensure LXD is installed and running.` |
| Environment already exists | `Error: Environment 'myproject' already exists. Use --force to reinitialise.` |
| `workshop.yaml` already exists | `Error: workshop.yaml already exists in this directory. Use --force to overwrite.` |
| `opencode.jsonc` already exists | `Error: opencode.jsonc already exists in this directory. Use --force to overwrite.` |
| Workspace not writable | `Error: Cannot write to current directory: <reason>` |
| Workshop create fails | `Error: Workshop environment creation failed: <workshop stderr>` |
| Post-creation verification fails | `Error: Environment 'myproject' was not found after creation. Workshop output: <detail>` |

---

## Files Written

| File | Condition | Location |
|------|-----------|----------|
| `workshop.yaml` | Always | `<cwd>/workshop.yaml` |
| `opencode.jsonc` | Only when `--agent opencode` | `<cwd>/opencode.jsonc` |
| `.microjail/state.json` | Always (after successful creation) | `<cwd>/.microjail/state.json` |

**Write order** (FR-011):
1. `workshop.yaml`
2. `opencode.jsonc` (if applicable)
3. `workshop create <yaml>` subprocess call
4. Post-creation verification via `lxc info <name>` subprocess (exit code 0 = success)
5. `.microjail/state.json`

If step 3 or 4 fails and files were written in steps 1–2, those files are left in place
(they are valid config files). The user can re-run with `--force` or remove them manually.
State is never written on failure.

---

## Help Output (`microjail init --help`)

```
Usage: microjail init [OPTIONS] NAME

  Create a Workshop environment and write configuration files for a jailed
  workload session.

  NAME is the environment name; it must start with a letter and contain only
  letters, digits, and hyphens (max 63 characters).

Options:
  --inference [llama-cpp]   Configure a local inference backend.
  --agent [opencode]        Configure an AI agent harness.
  --force                   Overwrite existing workshop.yaml and opencode.jsonc.
  --help                    Show this message and exit.

Examples:
  microjail init myproject
  microjail init myproject --inference llama-cpp --agent opencode
```

---

## Invariants

These invariants MUST hold after any successful `microjail init` invocation:

1. A Workshop/LXD environment named `<NAME>` exists and is confirmed by `lxc info <NAME>`
   returning exit code 0.
2. `workshop.yaml` exists in the working directory and is valid YAML with the correct schema.
3. If `--agent opencode` was passed, `opencode.jsonc` exists and contains no enabled remote
   provider entries.
4. `.microjail/state.json` exists, is valid JSON, and `state.name == NAME`.
5. The command exited with code 0.

If any invariant is violated, the test is a failure regardless of exit code.
