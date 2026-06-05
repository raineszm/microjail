# Research: Simplify Exception Handling

**Feature**: `specs/20260605-095056-simplify-exception-handling`
**Date**: 2026-06-05

---

## 1. ExitStack callback exception semantics

**Decision**: Cleanup callbacks that can fail (e.g. `unlock_egress`, `workshop_client.remove`)
MUST catch their own exceptions internally and print a warning. They MUST NOT let the exception
propagate to ExitStack.

**Rationale**: `contextlib.ExitStack.__exit__` calls registered callbacks in LIFO order and
runs *all* of them regardless of individual failures. However, if a callback raises an
unhandled exception, ExitStack stores it and at the end re-raises the *last* exception seen
(subject to chaining rules). For the CTF runner, cleanup failures are warnings — they must not
become a fatal error that changes the recorded `outcome`. Absorbing exceptions inside the
callback (with an inline `try/except` + console warn) keeps ExitStack clean and the outcome
field accurate.

**Alternatives considered**:
- Let ExitStack propagate: rejected — would change outcome from `"pass"/"fail"` to `"error"` on
  spurious cleanup failures, defeating the test result.
- `stack.enter_context(contextlib.suppress(Exception))` around each call: rejected — this
  swallows silently, violating Constitution §V.
- External `try/except` per callback in the finally: current approach — replaced by this refactor.

---

## 2. Helper placement

**Decision for `load_state_or_exit`**: Place in `src/microjail/commands/__init__.py`.

**Rationale**: The function is consumed exclusively by command modules (`lock`, `unlock`, `run`).
`commands/__init__.py` currently contains only a docstring — it's the natural home for package-level
utilities. No circular import risk since commands do not import each other.

**Decision for `resolve_project`**: Place in `src/microjail/gates/__init__.py`.

**Rationale**: `GateResult` is defined there; all gate modules already import from it. Adding
`resolve_project` to the same file avoids a new module and keeps `GateResult` construction
co-located with its type definition. The leading underscore signals it is package-internal.

**Alternatives considered**:
- New `src/microjail/commands/_state.py`: rejected — unnecessary module for 8 lines.
- New `src/microjail/gates/_helpers.py`: rejected — same reason; `__init__.py` is already
  the shared infrastructure file for the gates package.

---

## 3. ExitStack registration order for CTF cleanup

**Decision**: Register resources in acquisition order so LIFO cleanup matches the original
`finally` intent. Workspace `rmtree` is registered first (runs last); proc termination is
registered last (runs first).

**Acquisition → cleanup order**:

```
Acquired         Registered    Cleaned (LIFO)
─────────────    ──────────    ──────────────
workspace          1st    →    6th (last): rmtree(workspace, ignore_errors=True)
env launch         2nd    →    5th: cleanup_env (warn on failure)
env launch         3rd    →    4th: cleanup_egress (warn on failure)
tmp_secret_path    4th    →    3rd: tmp_secret_path.unlink(missing_ok=True)
server             5th    →    2nd: server.server.shutdown (suppress Exception)
proc               6th    →    1st: terminate_proc (suppress Exception)
```

**Rationale**: This replicates the original `finally` cleanup order exactly. Workspace rmtree
must be last because `cleanup_env` and `cleanup_egress` reference path objects under
`workspace`. Proc termination runs first because it is the most time-sensitive (stops the agent
before releasing the network).

**Note on `server.server.shutdown` placement**: The server is started after `lock_egress` in the
current code — but that's inside the `try` block, and the registration must happen at the point
of acquisition, not at some later point. The ExitStack refactor naturally co-locates these.

---

## 4. `write_config_files` consolidation approach

**Decision**: Wrap all three writes in a single `try` block with a single `except OSError` handler.

**Rationale**: All three writes share the same error message (`"Cannot write to current directory"`)
and the same handler (`err(..., code=3)`). A single `try` over sequential writes is idiomatic
Python and passes ruff's `SIM` checks. There is no need to distinguish *which* write failed in
the error message — the OSError already carries the file path.

**Alternatives considered**:
- Context manager per write: rejected — adds abstraction for no gain.
- Extract a `write_or_exit(path, content, code)` helper: considered but rejected — the three
  writes are grouped in one function and the single-try form is already maximally clear.

---

## 5. Message text preservation for gates

**Decision**: The `resolve_project` helper in `gates/__init__.py` uses a generic
`"Cannot determine LXD project to run {gate_name} check: {exc}. Ensure Workshop and LXD are running."`
message, replacing the per-gate hardcoded variants.

**Rationale**: Current per-gate messages differ only in the context clause (e.g.
`"to run egress probe"` vs `"to check workspace mount"`). Existing tests assert `passed=False`
and check `gate_name` — none assert the exact message text. A single generic message is
therefore safe and eliminates the per-gate duplication.

**Verified by**: Inspection of `tests/unit/gates/test_gates_egress.py`,
`tests/unit/gates/test_gates_workspace.py`, `tests/unit/gates/test_gates_state_readonly.py` —
all assert `result.passed is False` and `result.name == "..."`, not the message string.

---

## 6. `unlock_after_run` in `commands/run.py`

**Decision**: Consolidate the two sequential `try/except` blocks into a single `try` with two
`except` clauses.

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

**Rationale**: The conditional dependency (`state.dump` should only run when `unlock_egress`
succeeds) is naturally preserved: if `unlock_egress` raises `RuntimeError`, execution exits
the `try` body before `state.locked = False` or `state.dump` are reached. This is identical
control flow to the current two-block form. The single-try pattern is cleaner and was
previously deferred on the mistaken assumption that it would change behaviour.

User clarification (2026-06-05): "In some cases with multiple try/except blocks we can simplify
by wrapping the whole thing in a try/except and then handling different specific errors. Also
the code doesn't have to be entirely equivalent. It's okay to change things slightly as long as
we have the same safety guarantees." — this directly unblocks the consolidation.

**Safety check**: On `unlock_egress` failure — `state.locked` remains `True` in memory and on
disk (from `perform_lock`). Correct: the container IS locked because unlock failed. The warning
directs the user to run `microjail unlock` manually. Behaviour is identical to the old code.
---

## Summary of decisions

| # | Decision | Source |
|---|----------|--------|
| 1 | CTF cleanup callbacks absorb exceptions internally + warn | §1 |
| 2 | `load_state_or_exit` → `commands/__init__.py` | §2 |
| 3 | `resolve_project` → `gates/__init__.py` | §2 |
| 4 | ExitStack LIFO = workspace-last, proc-first | §3 |
| 5 | `write_config_files`: single `try` block | §4 |
| 6 | Generic gate error message via `resolve_project` | §5 |
| 7 | `unlock_after_run`: single `try` with two `except` clauses (was: deferred) | §6 |
