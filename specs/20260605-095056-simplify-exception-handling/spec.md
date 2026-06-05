# Feature Specification: Simplify Exception Handling

**Feature Branch**: `20260605-095056-simplify-exception-handling`

**Created**: 2026-06-05

**Status**: Draft

**Input**: User description: "There is a lot of try, except noise in the codebase currently. It can probably be significantly simplified using context managers for resource cleanup and ExitStacks to nest resource scopes. Lets identify the key places to do this and how to go about it"

---

## Background

Several recurring `try/except` patterns in `src/microjail/` and `ctf/` inflate code volume without adding clarity. The patterns fall into two categories:

1. **Resource cleanup guards**: `finally` blocks with nested `try/except` to suppress errors during teardown.
2. **Repeated error-conversion boilerplate**: identical `try/except` blocks that translate exceptions into an `err()` or `GateResult` call, repeated at every call site.

Addressing these with context managers and `ExitStack` makes cleanup guarantees explicit, reduces structural noise, and removes the risk of a cleanup error in one branch silently hiding an error from another.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — CTF runner cleanup uses ExitStack (Priority: P1)

A developer reading `ctf/main.py` encounters the test lifecycle. Currently Phase 4 (cleanup in `finally`) contains two nested `try/except` blocks—one for `unlock_egress` and one for `workshop_client.remove`—alongside `contextlib.suppress` calls and bare `if x is not None:` guards.

The cleanup sequence is replaced by an `ExitStack` populated during Phase 1 setup. Each resource that needs teardown registers a `stack.callback(...)` at the point it is acquired. The `finally` block shrinks to a single `stack.close()` (or the `with` statement handles it automatically).

**Why this priority**: The CTF runner is the most complex cleanup path in the codebase; it has the highest risk of a bug in cleanup logic silently masking a test-result error. Consolidating it is the highest-value change.

**Independent Test**: Can be fully tested by running the CTF test suite against a live environment and confirming all four outcome paths (`pass`, `fail`, `error`, `inconclusive`) exercise cleanup without leaving orphaned resources or masking errors.

**Acceptance Scenarios**:

1. **Given** a CTF run that succeeds, **When** cleanup runs, **Then** `unlock_egress`, `workshop_client.remove`, temp-file deletion, HTTP server shutdown, and workspace removal all execute without requiring `if x is not None` guards scattered through the `finally` block.
2. **Given** `unlock_egress` raises during cleanup, **When** the ExitStack handles it, **Then** `workshop_client.remove` still runs (i.e., one failing callback does not abort the rest), and the warning is still printed.
3. **Given** a SIGINT or SIGTERM arrives during Phase 2/3, **When** the shutdown event is set and the `with ExitStack()` block exits, **Then** the same cleanup path runs as for a normal exit.
4. **Given** setup fails before all resources are acquired, **When** the ExitStack exits, **Then** only the callbacks that were actually registered execute (no `AttributeError` on `None`).

---

### User Story 2 — `write_config_files` uses a single OSError guard (Priority: P2)

A developer maintaining `src/microjail/commands/init.py` currently sees three structurally identical `try/except OSError → err()` blocks for three sequential file-write operations inside `write_config_files`. All three have the same handler body.

The three blocks are collapsed into one `try` covering all writes (or the writes are extracted into a helper that wraps the entire sequence). The handler fires once with a meaningful message.

**Why this priority**: Removing duplicate exception structure reduces the chance of one branch diverging from the others over time.

**Independent Test**: Can be fully tested by unit-testing `write_config_files` with a read-only target directory and confirming the correct error message is produced regardless of which write fails.

**Acceptance Scenarios**:

1. **Given** `.workshop/` is not writable, **When** `write_config_files` is called, **Then** exactly one `err()` call fires with a clear message.
2. **Given** the primary `.yaml` write succeeds but the SDK write fails, **When** `write_config_files` is called, **Then** `err()` fires with the OSError details.
3. **Given** all writes succeed, **When** `write_config_files` is called, **Then** no exception is raised and the function returns normally.

---

### User Story 3 — Gate files share a `_workshop_project()` error handler (Priority: P3)

Three gate modules (`egress.py`, `state_readonly.py`, `workspace.py`) each open with:

```python
try:
    project = _workshop_project()
except RuntimeError as exc:
    return GateResult(name="...", passed=False, message=f"Cannot determine LXD project: {exc}. ...")
```

The three blocks are structurally identical except for the gate name. A shared helper (context manager or plain function) converts the `RuntimeError` to a `GateResult` in one place.

**Why this priority**: Purely mechanical deduplication; each gate still needs its own gate-name string, so no correctness risk, but consolidating means a future change to the error message only happens in one place.

**Independent Test**: Can be fully tested by mocking `_workshop_project` to raise and confirming each gate returns the correct `passed=False` `GateResult` with the expected gate name.

**Acceptance Scenarios**:

1. **Given** `_workshop_project()` raises `RuntimeError`, **When** any of the three gates run, **Then** each returns a `GateResult(passed=False)` containing the gate's own name and the RuntimeError message.
2. **Given** `_workshop_project()` succeeds, **When** any of the three gates run, **Then** the gate proceeds to the subprocess check (no early return).

---

### User Story 4 — Command entry points use a shared state-loading helper (Priority: P4)

`lock()`, `unlock()`, and `run()` each open with:

```python
try:
    state = State.from_json(workspace)
    ...
except FileNotFoundError:
    err("No microjail environment found...")
except RuntimeError as exc:
    err(str(exc))
```

A helper (context manager or function) centralises this pattern so adding a new command does not require copy-pasting it.

**Why this priority**: Low risk, low complexity; the pattern is already consistent, so the main win is preventing future drift.

**Independent Test**: Can be fully tested by running each command against a workspace with no `state.json` and confirming the correct exit code and message.

**Acceptance Scenarios**:

1. **Given** `.microjail/state.json` does not exist, **When** any of the three commands run, **Then** a single consistent error message is printed and the process exits non-zero.
2. **Given** `State.from_json` raises `RuntimeError`, **When** any of the three commands run, **Then** the error message is forwarded and the process exits non-zero.

---

### Edge Cases

- What happens when an `ExitStack` callback itself raises — does it suppress subsequent callbacks or propagate? The ExitStack contract is that all callbacks run; only the last exception propagates (Python stdlib behaviour). Any cleanup that must warn rather than raise must use `contextlib.suppress` or catch inside the callback itself.
- How does the refactor interact with the existing `contextlib.suppress(Exception)` calls already present in `lock.py` and `ctf/main.py`? Those should remain where suppression is intentional; the refactor targets `try/except` blocks that duplicate boilerplate, not ones with deliberate suppress semantics.
- If `perform_lock` is called from both `lock()` and `run()`, does centralising state-loading in each command entry point affect `perform_lock`? No — `perform_lock` takes an already-loaded `State` object and is unchanged by this refactor.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The `ctf/main.py` cleanup path MUST use `contextlib.ExitStack` to register teardown callbacks at resource-acquisition time, replacing the nested `try/except` blocks in the `finally` clause.
- **FR-002**: The ExitStack MUST ensure all registered callbacks execute even when an earlier callback raises, preserving the current best-effort cleanup behaviour.
- **FR-003**: Warning messages for CTF cleanup failures MUST be preserved verbatim: the `unlock_egress` failure warning and the `workshop remove` failure warning in `ctf/main.py` MUST print the same text as today. Warning and error messages in gate modules and `write_config_files` MAY change slightly in phrasing as long as they remain accurate and actionable.
- **FR-004**: `write_config_files` in `src/microjail/commands/init.py` MUST consolidate its three `try/except OSError` blocks into at most one structured error boundary.
- **FR-005**: The three gate files (`egress.py`, `state_readonly.py`, `workspace.py`) MUST share a single point-of-definition for the `_workshop_project()` error-to-`GateResult` conversion, rather than repeating it per file.
- **FR-006**: The `FileNotFoundError` / `RuntimeError` → `err()` pattern at command entry points (`lock`, `unlock`, `run`) MUST be expressed once, not copy-pasted across three files.
- **FR-007**: All existing tests MUST continue to pass after the refactor without modification. The sole exception: if a test currently asserts the exact text of a non-safety-critical message (e.g. a gate error string) and that message changes slightly as a safe consequence of consolidation, that test assertion MAY be updated to match the new phrasing — provided the safety guarantee (the `passed` field and gate name) is unchanged. Assertions on exit codes, `result.passed`, `result.name`, and state fields are immutable and MUST NOT be changed.
- **FR-008**: The refactor MUST preserve the same safety guarantees: correct exit codes, state consistency (locked/unlocked), and cleanup running on every exit path. Exact output string equivalence is NOT required except for the CTF warning messages covered by FR-003.

### Key Entities

- **ExitStack** (`contextlib.ExitStack`): the standard-library mechanism for stacking context managers and callbacks so they all run on exit regardless of which one raises. Relevant to FR-001/FR-002.
- **GateResult**: the dataclass returned by each gate check (`passed: bool`, `name: str`, `message: str`). The shared helper in FR-005 constructs this.
- **State**: the on-disk JSON record of the current microjail environment. The state-loading boilerplate in FR-006 reads and raises on its behalf.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The `finally` block in `ctf/main.py` shrinks from ≥6 conditional/try/except clauses to ≤2 statements (`stack.close()` or the `with` exit, plus any intentional suppressions).
- **SC-002**: `write_config_files` contains exactly one `except OSError` clause after the refactor (down from three).
- **SC-003**: The `_workshop_project()` error-handling code exists in exactly one location in the codebase after the refactor (down from three identical copies).
- **SC-004**: The `FileNotFoundError`/`RuntimeError` → `err()` command-entry pattern exists in exactly one location after the refactor (down from three identical copies in `lock.py`, `unlock.py`, `run.py`).
- **SC-005**: All existing unit and integration tests pass. Minor updates to test assertions that check non-safety-critical message text are acceptable; test assertions on exit codes, `result.passed`, `result.name`, and state fields are immutable.
- **SC-006**: Exit codes are unchanged on every code path. Safety-relevant state transitions (lock, unlock, state.json content) are unchanged. Non-safety output strings (gate messages, `write_config_files` error text) MAY differ slightly from today.

---

## Assumptions

- The refactor may introduce slight changes to non-safety-critical output text (e.g., gate error message phrasing, `write_config_files` error detail). Such changes are acceptable provided no existing test asserts the changed text and the safety guarantee is maintained.
- `contextlib.ExitStack` and `contextlib.suppress` from the Python standard library are sufficient; no third-party library is needed.
- The gate helper introduced for FR-005 lives in `src/microjail/gates/__init__.py` or a new `src/microjail/gates/_helpers.py`; the exact location is an implementation decision.
- The state-loading helper for FR-006 may be a bare function (e.g. `load_state_or_exit`) rather than a full context manager, since no resource needs releasing after the load.
- The CTF runner's `proc.terminate()` / `proc.wait()` pattern (already using `contextlib.suppress`) is idiomatic and does not need to change.
- Tests will be run with `pytest` against the existing test suite; no new integration infrastructure is required.

---

## Clarifications

### Session 2026-06-05

- Q: Must all code changes be byte-for-byte equivalent to existing behaviour, or is slight variation acceptable? → A: Slight variation is acceptable as long as the same safety guarantees are maintained (correct exit codes, state consistency, cleanup on every exit path). Exact message-text equivalence is NOT required except for the two named CTF cleanup warnings.
- Q: Can multiple sequential try/except blocks be collapsed into a single try with multiple except clauses? → A: Yes. Where operations are logically dependent (later operations should not run if earlier ones fail), a single try block with per-exception handlers is the preferred consolidation approach — the control-flow dependency is naturally preserved because a raise in the try body exits before later statements execute.
