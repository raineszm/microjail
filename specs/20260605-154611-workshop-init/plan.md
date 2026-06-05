# Implementation Plan: Thin-Wrapper Init with Lazy Container Launch

**Branch**: `20260605-154611-workshop-init` | **Date**: 2026-06-05 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/20260605-154611-workshop-init/spec.md`

## Summary

Two-part structural refactor of `src/microjail/commands/init.py` and `src/microjail/commands/lock.py`. No new user-facing flags. No changes to output format or exit codes beyond what the spec requires.

**Part 1 — Thin wrapper**: `microjail init` stops calling `workshop launch`, `verify_exists`, and `workshop connect`. It becomes a pure config-file writer: validate → write YAML/jsonc/state → exit. All Workshop subprocess calls are deferred to the first `lock` or `run`.

**Part 2 — Lazy launch**: `perform_lock` gains a new pre-step (`ensure_container_ready`) that provisions the container on first use when `state.launched=False`. `State` gains a `launched: bool` field (default `True` for backward compat with existing state files).

**Targets in priority order**:

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| P1 | `state.py` | Missing `launched` field | Add `launched: bool = field(default=True)` |
| P2 | `commands/init.py` | Calls `workshop launch`, `verify_exists`, `connect` on normal path | Remove `launch_and_verify()`; restructure `preflight()` and `init()` |
| P3 | `wrappers/workshop.py` | No `ensure_launched` helper | Add `ensure_launched(name, project_dir)` |
| P4 | `commands/lock.py` | `perform_lock` does not handle unlaunched envs | Add `ensure_container_ready` helper; insert call at top of `perform_lock` |
| P5 | `tests/unit/state/` | No coverage for `launched` field | Add `test_state_launched_field.py` |
| P6 | `tests/unit/commands/test_preconditions.py` | Tests break due to changed init orchestration | Replace 4 tests; add 2 new tests |
| P7 | `tests/unit/commands/test_lock_command.py` | No coverage for lazy-launch path in lock | Add 3 lazy-launch unit tests |
| P8 | `tests/integration/commands/` | Fixtures assume init leaves a launched env | Update `conftest.py` fixtures; update init integration tests |

## Technical Context

**Language/Version**: Python 3.14 (`requires-python = ">=3.14"`)

**Primary Dependencies**: `msgspec >= 0.21.1` (State serialization), `typer >= 0.25.0` (CLI), `ruamel-yaml >= 0.19.1` (workshop YAML generation). All existing runtime deps; no new dependencies.

**Storage**: `.microjail/state.json` — gains `launched` boolean field. Backward-compatible: absent key deserializes as `True` (msgspec field default).

**Testing**: `pytest >= 9.0.3`. Existing test files in `tests/unit/` and `tests/integration/commands/`. Long-running integration tests require `--run-long` and live Workshop + LXD.

**Target Platform**: Linux (host machine running Workshop + LXD).

**Project Type**: CLI tool (`microjail` entry point) + library of wrappers/gates.

**Performance Goals**: `microjail init` must complete in under 2 seconds (SC-001). Zero Workshop/LXD subprocesses on normal init path (SC-002).

**Constraints**:
- Observable CLI behaviour (exit codes, output strings) MUST be byte-for-byte identical except where the spec explicitly changes them (no `workshop info` success after bare init).
- `state.json` `launched` field default (`True`) ensures all existing persisted states decode correctly without migration.
- No new `# noqa` suppressions (constitution §IV).
- `ruff` must report zero diagnostics on changed files.
- `perform_lock` remains the single chokepoint for both `lock` and `run` — the lazy-launch logic MUST live there.

**Scale/Scope**: 4 source files modified (`state.py`, `commands/init.py`, `commands/lock.py`, `wrappers/workshop.py`); 1 new unit test file (`test_state_launched_field.py`); 2 unit test files updated (`test_preconditions.py`, `test_lock_command.py`); integration test fixtures updated.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment | Notes |
|-----------|------------|-------|
| **I — Safety First** | ✅ PASS | `perform_lock` remains the single gate. `ensure_container_ready` inserts before `lock_egress`, not after. `launched=True` is persisted before any LXD mutation (FR-008), so a crash between provisioning and locking leaves state truthful and the next `lock` skips the re-launch. Gate logic unchanged. |
| **II — Correctness Over Confidence** | ✅ PASS | `verify_exists` is still called after every `launch` (in `ensure_launched`). The postcondition is still independently verified — just at lock/run time rather than init time. `init --force` on a launched env still calls `verify_exists` after `refresh`. No verification step is removed; only the timing changes. |
| **III — Human Readability & Auditability** | ✅ PASS | `ensure_container_ready` and `ensure_launched` describe intent. `perform_lock` gains a clearly labelled Step 0. The `launched` field name unambiguously describes the lifecycle state. `launch_and_verify` is deleted, not hidden. |
| **IV — Idiomatic Python** | ✅ PASS | `field(default=True)` is the standard `msgspec` pattern for backward-compatible optional fields. No `# noqa` required. Type annotations on all new functions. |
| **V — Fail Loudly, Fail Clearly** | ✅ PASS | All new failure paths exit non-zero with actionable messages: `--force` on locked env exits 2 naming the fix; launch failure exits 3 with Workshop output; connect failure exits 3 naming the tunnel; drift detection surfaces via `_container_name` RuntimeError naming `workshop status`. No exception is swallowed. |
| **Security & Isolation** | ✅ PASS | Audit trail unchanged (`run-log.jsonl`). Egress is still confirmed down by the egress gate before the workload spawns. `launched=True` persisted before `lock_egress` ensures state is always truthful, avoiding a window where the container exists but `locked=False` is written after a crash. |

No violations. No Complexity Tracking entry required.

## Project Structure

### Documentation (this feature)

```text
specs/20260605-154611-workshop-init/
├── plan.md               # This file
├── spec.md               # Feature specification
├── research.md           # Phase 0 output
├── data-model.md         # Phase 1 output
├── contracts/
│   └── cli-commands.md   # Phase 1 output — command behavioural contracts
└── checklists/
    └── requirements.md   # Specification quality checklist
```

*`quickstart.md` is omitted: this is a pure refactor with no new user-facing behaviour. `tasks.md` is not produced by this command.*

### Source Code (repository root)

```text
src/microjail/
├── state.py                 # + launched: bool = field(default=True)
├── commands/
│   ├── init.py              # Remove launch_and_verify(); restructure preflight() + init()
│   └── lock.py              # + ensure_container_ready(); perform_lock gains Step 0
└── wrappers/
    └── workshop.py          # + ensure_launched(name, project_dir)

tests/
├── unit/
│   ├── state/
│   │   └── test_state_launched_field.py     # NEW — 5 tests mirroring locked field pattern
│   └── commands/
│       ├── test_preconditions.py            # UPDATED — 4 tests replaced, 2 new tests added
│       └── test_lock_command.py             # UPDATED — 3 lazy-launch tests added
└── integration/
    └── commands/
        ├── conftest.py                      # UPDATED — fixtures call lock after init
        └── test_init_command.py             # UPDATED — init no longer implies env exists
```

**Structure Decision**: Single-project layout. No new top-level packages. `ensure_container_ready` lives in `commands/lock.py` (used exclusively via `perform_lock`); `ensure_launched` lives in `wrappers/workshop.py` (subprocess logic). No new modules.

---

## Phase 0: Research

*All findings consolidated in [`research.md`](./research.md).*

---

## Phase 1: Design

*`data-model.md` and `contracts/cli-commands.md` produced above.*

### Interface Designs

#### `State.launched` — `src/microjail/state.py`

```python
launched: bool = field(default=True)
```

`default=True` for backward compatibility: all pre-existing `state.json` files were written after a successful launch, so an absent key means "already launched." New `init` writes `launched=False` explicitly.

Precedes `locked` in field order to keep related lifecycle fields adjacent.

#### `workshop.ensure_launched` — `src/microjail/wrappers/workshop.py`

```python
def ensure_launched(name: str, project_dir: Path) -> None:
    """Provision the Workshop environment *name*, then verify it exists.

    Calls ``check_prerequisites()``, ``workshop launch <name>``, then
    ``workshop info <name>`` (constitution §II: verify the postcondition).

    Raises :exc:`RuntimeError` with an actionable message on any failure.
    The caller is responsible for persisting ``State.launched = True``
    after this returns — state mutation belongs in the command layer.
    """
    check_prerequisites()
    launch(name, project_dir)
    verify_exists(name, project_dir)
```

#### `ensure_container_ready` — `src/microjail/commands/lock.py`

```python
def ensure_container_ready(state: State, workspace: Path) -> None:
    """Launch the Workshop container on first use and connect the inference tunnel.

    Only called when ``state.launched`` is ``False``.  On return the container
    is running, ``state.launched`` is persisted as ``True``, and (when inference
    is configured) the tunnel is wired.

    FR-008: ``state.launched`` is persisted before any LXD mutation so a crash
    after provisioning but before locking leaves the state file truthful.
    """
    from microjail.config.workshop import INFERENCE_PLUG_REF, INFERENCE_SLOT_REF

    workshop.ensure_launched(state.name, workspace)
    state.launched = True
    state.dump(workspace)          # persist before any LXD call (FR-008)
    if state.inference is not None:
        workshop.connect(state.name, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF, workspace)
```

#### `perform_lock` update — `src/microjail/commands/lock.py`

Insert one block at the top:

```python
def perform_lock(state: State, workspace: Path) -> None:
    # Step 0 (new): ensure container exists, launching on first use.
    if not state.launched:
        ensure_container_ready(state, workspace)

    # Step 1 (unchanged): cut egress.
    lock_egress(state.name, workspace)
    # Steps 2–4 unchanged …
```

#### `init()` restructuring — `src/microjail/commands/init.py`

`preflight()` changes:
- **Remove**: `workshop.check_prerequisites()` call
- **Remove**: `workshop.environment_exists()` call and its `already_exists` return value
- **Add**: Read existing `state.json` when `--force` to detect `launched` and `locked`
- **Add**: Exit 2 when `--force` and `state.locked=True` (FR-017)
- **Keep**: `os.access(workspace, os.W_OK)` check
- **Keep**: Local file-conflict checks (state.json, .workshop/<name>.yaml, opencode.jsonc)

`init()` changes:
- **Remove**: call to `launch_and_verify()`
- **Remove**: `workshop.connect()` call on normal path
- **Add**: When `--force` and `state.launched=True`: call `workshop.check_prerequisites()`, `workshop.refresh()`, `workshop.verify_exists()`, `workshop.connect()` (if inference)
- **Change**: `State(...)` constructed with `launched=False` (explicit, not defaulted)

`launch_and_verify()` function: **deleted**.

#### `preflight()` return type change

`preflight()` currently returns `bool` (`already_exists`). After this change it returns `None` — the `--force` branching in `init()` reads state from disk directly rather than using the return value of `preflight`.

---

## Phase 2: Tasks

*`tasks.md` is produced by the `/speckit.tasks` command — not created here.*
