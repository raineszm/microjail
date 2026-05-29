# Implementation Plan: microjail init Command

**Branch**: `main` | **Date**: 2026-05-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/20260529-154152-init-command/spec.md`

## Summary

Implement `microjail init <name> [--inference llama-cpp] [--agent opencode]` — the entry-point
command that creates a Workshop/LXD environment, writes `workshop.yaml` and (optionally)
`opencode.jsonc` to the workspace, and persists environment state to `.microjail/state.json`.
All file writes happen before the Workshop environment is created to prevent partial state.
The command verifies the environment actually exists after creation; it never assumes success
from the absence of an error.

## Technical Context

**Language/Version**: Python 3.14 (per `pyproject.toml`, `requires-python = ">=3.14"`)

**Primary Dependencies**:
- `typer` — CLI framework (already declared)
- `rich` — terminal output (already declared)
- `ruamel.yaml` — `workshop.yaml` serialisation (needs adding to `pyproject.toml`)
- `stdlib: json, pathlib, dataclasses, subprocess` — state file, config generation,
  Workshop and LXD CLI invocation

Note: `pylxd` is NOT used for this feature. Post-creation verification uses `lxc info`
via subprocess. The `pylxd` dependency in `pyproject.toml` may be removed if no other
feature requires it.

**Storage**: JSON files (`.microjail/state.json`, `opencode.jsonc`) and YAML (`workshop.yaml`)
written to the workspace directory (current working directory at invocation time).

**Testing**: pytest + anyio (already in dev dependencies). LXD-dependent tests marked
`@pytest.mark.lxd` per existing `pyproject.toml` marker registration. Unit tests mock
subprocess and filesystem; integration tests require a live Workshop + LXD installation.

**Target Platform**: Linux (Ubuntu). Workshop and LXD are Linux-only prerequisites.

**Project Type**: CLI tool

**Performance Goals**: Full `microjail init` (including Workshop environment creation) MUST
complete within 60 seconds on a local machine with Workshop and LXD already installed (SC-001).
File-generation steps alone (workshop.yaml, opencode.jsonc, state.json) MUST complete in
under 1 second.

**Constraints**:
- FR-011: all local file writes MUST succeed before any Workshop CLI call is made.
- No network calls from microjail itself; all Workshop and LXD API access is via local subprocess.
- No TCP tunnel in `workshop.yaml`; inference uses UDS bind-mount path.

**Scale/Scope**: Single-user, single-environment CLI tool. One environment per workspace.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Safety First | ✅ PASS | FR-011 enforces write-before-create ordering. FR-007 verifies postcondition. FR-008/009 fail loudly before any state is mutated. |
| II. Correctness Over Confidence | ✅ PASS | Workshop environment existence is verified via `pylxd` after `workshop create`, not assumed. Prerequisite checks probe actual tool availability, not PATH presence alone. |
| III. Human Readability & Auditability | ✅ PASS | Named modules per concern (config, state, workshop client). All error messages name the specific failure and the remediation. |
| IV. Idiomatic Python | ✅ PASS | `dataclasses` for state, `pathlib` for all path operations, `typer` for CLI, full type annotations required. |
| V. Fail Loudly, Fail Clearly | ✅ PASS | Every error path exits non-zero. FR-002/003 validate enum values before any I/O. FR-009 names missing prerequisites explicitly. |

No violations. No Complexity Tracking entry required.

*Post-Phase-1 re-check*: No new violations introduced. Workshop client is a thin subprocess
wrapper — no hidden abstraction layers. Config generators are pure functions with no side
effects, trivially testable.

## Project Structure

### Documentation (this feature)

```text
specs/20260529-154152-init-command/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── cli.md           # CLI interface contract
└── tasks.md             # Phase 2 output (/speckit.tasks — not created here)
```

### Source Code (repository root)

```text
src/microjail/
├── __init__.py
├── cli.py                       # typer app root; registers init command
├── commands/
│   └── init.py                  # init command: orchestrates config gen + workshop create
├── config/
│   ├── opencode.py              # opencode.jsonc generation (pure function)
│   └── workshop.py              # workshop.yaml generation (pure function)
├── state.py                     # EnvironmentState dataclass; read/write state.json
└── workshop/
    └── client.py                # thin subprocess wrapper for `workshop` CLI

tests/
├── unit/
│   ├── test_config_opencode.py  # opencode.jsonc content correctness
│   ├── test_config_workshop.py  # workshop.yaml content correctness
│   └── test_state.py            # state read/write round-trip
└── integration/
    └── test_init_command.py     # end-to-end; requires @pytest.mark.lxd
```

**Structure Decision**: Single-project layout. `commands/` holds one module per CLI command
(scales cleanly as `run`, `unlock`, etc. are added). `config/` holds pure generators — no I/O,
easily unit-tested. `workshop/` holds all subprocess interaction, keeping it isolated and
mockable.
