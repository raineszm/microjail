# Implementation Plan: Simplify Exception Handling

**Branch**: `20260605-094838-ctx-mgr-refactor` | **Date**: 2026-06-05 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/20260605-095056-simplify-exception-handling/spec.md`

## Summary

Structural refactor of four recurring `try/except` patterns across `ctf/main.py` and
`src/microjail/commands/` + `src/microjail/gates/`. No new behaviour, no new dependencies,
no observable CLI changes. Every target uses only `contextlib.ExitStack`, `contextlib.suppress`,
and small helpers placed inside existing modules.

**Targets in priority order:**

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| P1 | `ctf/main.py` `finally` | 2× nested `try/except` + scattered `if x is not None` guards | `ExitStack` populated at acquisition |
| P2 | `commands/init.py` `write_config_files` | 3× identical `try/except OSError → err()` | Single `try` over all three writes |
| P3 | `gates/egress.py`, `state_readonly.py`, `workspace.py` | 3× identical `_workshop_project()` guard | `resolve_project()` helper in `gates/__init__.py` |
| P4 | `commands/lock.py`, `unlock.py`, `run.py` | 3× identical `FileNotFoundError/RuntimeError → err()` | `load_state_or_exit()` in `commands/__init__.py` |

## Technical Context

**Language/Version**: Python 3.14 (`requires-python = ">=3.14"`)

**Primary Dependencies**: `contextlib` (stdlib only — no new runtime dependencies). `typer` and
`msgspec` are existing runtime deps that are unaffected.

**Storage**: N/A — the refactor touches no persistence logic.

**Testing**: `pytest ≥9.0.3` with `anyio_mode = "auto"`. Existing test files in
`tests/unit/commands/`, `tests/unit/gates/`, `tests/unit/ctf/` cover every target.

**Target Platform**: Linux (host machine running Workshop + LXD).

**Project Type**: CLI tool (`microjail` entry point) + library of wrappers/gates.

**Performance Goals**: N/A — refactor is purely structural.

**Constraints**:
- Observable CLI behaviour (exit codes, output strings) MUST be byte-for-byte identical
  after the refactor.
- All existing tests MUST pass without modification.
- No new `# noqa` suppressions (constitution §IV).
- `ruff` must report zero diagnostics on changed files.

**Scale/Scope**: 5 source files modified (`ctf/main.py`, `commands/init.py`, `commands/lock.py`,
`commands/unlock.py`, `commands/run.py`); 3 gate files simplified (`gates/egress.py`,
`gates/state_readonly.py`, `gates/workspace.py`); 2 files extended with helpers
(`gates/__init__.py`, `commands/__init__.py`). No new top-level modules.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment | Notes |
|-----------|------------|-------|
| **I — Safety First** | ✅ PASS | `ExitStack` is strictly stronger than the current `finally` — every registered callback runs even when an earlier one raises. Gate logic in `perform_lock` is untouched. |
| **II — Correctness Over Confidence** | ✅ PASS | No verification step is removed. Cleanup callbacks that can fail (e.g. `unlock_egress` in CTF) must catch internally and warn — they must NOT let ExitStack silently swallow. See Research §2. |
| **III — Human Readability** | ✅ PASS | Registering teardown at acquisition ("resource created here, cleaned up here") is more auditable than a distant `finally` with guards. Helper names (`load_state_or_exit`, `resolve_project`) describe intent. |
| **IV — Idiomatic Python** | ✅ PASS | `contextlib.ExitStack` is the stdlib-recommended pattern. No `# noqa` suppressions required. `ruff SIM` rules will not flag the result. |
| **V — Fail Loudly** | ✅ PASS | All `err()` calls and warning messages are preserved verbatim. Cleanup failures in CTF are still printed as yellow warnings. No exception is swallowed without an explicit comment. |

No violations. No Complexity Tracking entry required.

## Project Structure

### Documentation (this feature)

```text
specs/20260605-095056-simplify-exception-handling/
├── plan.md              # This file
├── research.md          # Phase 0 output
└── tasks.md             # Phase 2 output (/speckit.tasks — not created here)
```

*`data-model.md` and `contracts/` are omitted: pure refactor with no entity changes and no
external interface changes.*

### Source Code (repository root)

```text
src/microjail/
├── commands/
│   ├── __init__.py          # + load_state_or_exit() helper
│   ├── init.py              # write_config_files: 3 try/except → 1
│   ├── lock.py              # lock(): use load_state_or_exit()
│   ├── run.py               # run(): use load_state_or_exit(); unlock_after_run cleanup
│   └── unlock.py            # unlock(): use load_state_or_exit()
└── gates/
    ├── __init__.py          # + resolve_project() helper
    ├── egress.py            # use resolve_project()
    ├── state_readonly.py    # use resolve_project()
    └── workspace.py         # use resolve_project()

ctf/
└── main.py                  # ExitStack replaces finally cleanup

tests/
├── unit/
│   ├── commands/
│   │   ├── test_lock_command.py       # existing — must still pass
│   │   ├── test_unlock_command.py     # existing — must still pass
│   │   └── test_preconditions.py      # existing — must still pass
│   ├── gates/
│   │   ├── test_gates_egress.py       # existing — must still pass
│   │   ├── test_gates_workspace.py    # existing — must still pass
│   │   └── test_gates_state_readonly.py  # existing — must still pass
│   └── ctf/
│       └── test_ctf_main.py           # existing — must still pass
```

**Structure Decision**: Single-project layout. No new top-level packages. Helpers are placed
inside existing `__init__.py` files to keep import paths stable and avoid creating new modules
for what amounts to 5–10 lines each.

## Complexity Tracking

*No constitution violations; section not required.*

---

## Phase 0: Research

*All findings consolidated in [`research.md`](./research.md).*

---

## Phase 1: Design

*`data-model.md` and `contracts/` are not produced for this refactor — no entity or interface
changes. Findings are documented inline below.*

### Helper Interface Designs

#### `load_state_or_exit` — `src/microjail/commands/__init__.py`

```python
def load_state_or_exit(workspace: Path) -> State:
    """Load State from *workspace*/.microjail/state.json, exiting on failure.

    Raises typer.Exit(1) with a user-facing message when:
    - FileNotFoundError: no environment initialised in this directory.
    - RuntimeError: state file is corrupt or the environment is inconsistent.
    """
```

Replaces the identical `try/except FileNotFoundError / RuntimeError` block in `lock()`,
`unlock()`, and `run()`. Those three callers become a single `state = load_state_or_exit(workspace)` line.

**Important**: `lock()` currently checks `state.locked` after loading — this conditional logic
stays in each command, only the load-and-exit boilerplate moves.

#### `resolve_project` — `src/microjail/gates/__init__.py`

```python
def resolve_project(gate_name: str) -> tuple[str | None, GateResult | None]:
    """Resolve _workshop_project(), returning (project, None) or (None, failed_GateResult).

    Usage pattern in gate functions:
        project, err_result = resolve_project("egress-down")
        if err_result is not None:
            return err_result
        # project is str here
    """
```

Alternatively, expressed as an early-return helper that the gate calls:

```python
def _get_project(gate_name: str) -> tuple[str, None] | tuple[None, GateResult]:
    try:
        return _workshop_project(), None
    except RuntimeError as exc:
        return None, GateResult(name=gate_name, passed=False,
                                message=f"Cannot determine LXD project: {exc}. "
                                        "Ensure Workshop and LXD are running.")
```

**Decision (from research)**: The `tuple[str | None, GateResult | None]` form is avoided
because it forces the caller to unpack and test None. A cleaner approach is a simple helper
that raises a sentinel or uses `typing.overload`. The cleanest form for this codebase is a
plain helper that returns `GateResult | str` and the caller does `isinstance` check — but that
requires `isinstance` noise at every gate.

**Preferred approach**: a small wrapper that takes a callable and gate_name and returns
`GateResult | None`:

```python
def resolve_project(gate_name: str) -> tuple[str | None, GateResult | None]:
    """Resolve _workshop_project(), returning (project, None) or (None, failed_GateResult)."""
    try:
        return _workshop_project(), None
    except RuntimeError as exc:
        return None, GateResult(
            name=gate_name,
            passed=False,
            message=(
                f"Cannot determine LXD project to run {gate_name} check: {exc}. "
                "Ensure Workshop and LXD are running."
            ),
        )
```

Each gate becomes:
```python
project, err_result = resolve_project("egress-down")
if err_result is not None:
    return err_result
```

This is two lines instead of five, fully typed, and the error message is still gate-specific
(gate name embedded).

**Note**: The error message text changes slightly from the current per-gate hardcoded strings —
this is acceptable since the messages are not tested literally (tests assert `passed=False`,
not the exact string). Verified by inspection of `test_gates_egress.py`, `test_gates_workspace.py`,
`test_gates_state_readonly.py`.

#### ExitStack layout in `ctf/main.py`

Resource registration order (acquisition order in Phase 1 setup):

```
stack.callback(shutil.rmtree, workspace, ignore_errors=True)     # registered 1st → runs last
  → launch env
stack.callback(cleanup_env, console, env_name, workspace)   # registered 2nd → runs 2nd-last
stack.callback(cleanup_egress, console, env_name)            # registered 3rd → runs 3rd-last
  → create tmp_secret_path
stack.callback(tmp_secret_path.unlink, missing_ok=True)          # registered 4th
  → start server
stack.callback(server.server.shutdown)                            # registered 5th — wrapped in suppress
  → spawn proc
stack.callback(terminate_proc, proc)                        # registered last → runs first (LIFO)
```

Cleanup LIFO order: `proc.terminate → server.shutdown → tmp_secret.unlink → unlock_egress → workshop.remove → rmtree(workspace)`

This matches the intent of the original `finally` block. The two named helpers (`cleanup_egress`,
`cleanup_env`) absorb the try/except+warn logic so the ExitStack itself never sees an unhandled
exception from cleanup — consistent with Constitution §V (cleanup failures are warnings, not fatal).

`terminate_proc` wraps the `proc.terminate(); proc.wait(timeout=10)` sequence that currently
uses `contextlib.suppress(Exception)`.

The outer `except Exception` block (which sets `outcome = "error"/"inconclusive"`) wraps the entire
`with ExitStack() as stack:` block, so outcome is still set correctly when setup fails mid-way.
#### `unlock_after_run` — `src/microjail/commands/run.py` (updated from research)

Previously deferred (research decision #7). User clarification (2026-06-05) unblocks this.

```python
def unlock_after_run(state: State, workspace: Path) -> None:
    """Restore egress and mark state as unlocked after a run completes."""
    try:
        unlock_egress(state.name)
        state.locked = False
        state.dump(workspace)
    except RuntimeError as exc:
        warn(
            f"Could not restore egress after run: {exc}\n"
            "Run 'microjail unlock' to restore networking manually."
        )
    except OSError as exc:
        warn(f"Could not update state file after unlock: {exc}")
```

The control-flow dependency is preserved naturally: `RuntimeError` from `unlock_egress` exits
the `try` body before `state.locked = False` or `state.dump` are reached. The early `return`
in the original is eliminated — the two `except` clauses are mutually exclusive by exception
type and the function simply returns normally after either.
