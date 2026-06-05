## Goal

Remove `launched: bool` and `locked: bool` from `State` / `state.json` entirely. Replace every read of those fields with live subprocess queries — no persistent lock/launch tracking.

## Constraints & Preferences

- Prototype phase — backward compatibility is NOT a concern
- No `# noqa` suppressions
- All unit tests must pass after the change
- Feature branch: `20260605-154611-workshop-init` (current branch, `81787b1`)
- Use `edit` for file modifications

## Progress

### Done

- [x] Approved plan written to `local://dynamic-lock-launched-state.md`
- [x] Full codebase read: `state.py`, `lock.py`, `unlock.py`, `init.py`, `run.py`, `lxd.py`, `workshop.py`, all relevant unit tests

### In Progress

- [ ] Nothing — plan was approved but execution turn was aborted before any file was touched

### Pending

All implementation work. Start from the top:

- [ ] `src/microjail/state.py` — remove `launched` and `locked` fields
- [ ] `src/microjail/wrappers/lxd.py` — add `is_egress_locked(env_name) -> bool`
- [ ] `src/microjail/commands/lock.py` — delete `ensure_container_ready`; rewrite `perform_lock` step 0; replace `state.locked` idempotency guard; remove step 4 state dump
- [ ] `src/microjail/commands/unlock.py` — replace `state.locked` guard; remove state mutation
- [ ] `src/microjail/commands/init.py` — remove `launched`/`locked` kwargs; replace force-guard and force-refresh logic
- [ ] `src/microjail/commands/run.py` — simplify `unlock_after_run`
- [ ] Tests — delete two test files, rewrite affected tests
- [ ] `uv run ruff check` + `uv run pytest tests/unit/ -v`

## Key Decisions

- **`is_egress_locked` detection signal**: presence of the `microjail-state-ro` named device on the container. `lock_egress` adds it; `unlock_egress` removes it. Already the exact write/remove cycle in `lxd.py`.
- **Graceful "container doesn't exist"**: `is_egress_locked` calls `_container_name` which raises `RuntimeError` if container not found → catch → return `False`. Safe to call before container exists.
- **`launched` replacement**: `workshop.environment_exists(name, workspace)` — already exists in `workshop.py` at line 88, calls `workshop info <name> --project <dir>`, returns `bool`.
- **FR-008 (persist before LXD mutation) is moot**: no state to corrupt. Crash after `workshop launch` but before `workshop connect` → next call sees `environment_exists=True` → skips launch → same failure mode as before.
- **`init --force` locked guard**: `lxd.is_egress_locked(name)` — if container doesn't exist returns `False` automatically, so the guard is naturally a no-op for never-launched envs.
- **`state.dump()` scope**: after this change, `state.dump()` only fires from `init`. Lock and unlock no longer touch the state file.
- **No backward compat**: old state files with `launched`/`locked` keys are silently ignored by msgspec (unknown fields ignored by default).

## Critical Context

### Current `State` struct (`src/microjail/state.py`)

```python
class State(msgspec.Struct):
    name: str
    base_image: str
    inference: str | None
    agent: str | None
    socket_url: str | None
    launched: bool = field(default=True)   # DELETE THIS
    locked: bool = field(default=False)    # DELETE THIS
```

### `is_egress_locked` to add to `src/microjail/wrappers/lxd.py` (after `unlock_egress` at line ~249)

```python
def is_egress_locked(env_name: str) -> bool:
    """Return True if the microjail-state-ro device is attached to env_name's container."""
    try:
        project = _workshop_project()
        container = _container_name(env_name)
    except RuntimeError:
        return False
    result = subprocess.run(
        ["lxc", "--project", project, "config", "device", "show", container],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    return _STATE_RO_DEVICE in result.stdout.decode()
```

`_STATE_RO_DEVICE = "microjail-state-ro"` is defined at line 30 of `lxd.py`.

### `lock.py` changes (`src/microjail/commands/lock.py`)

**Delete** `ensure_container_ready()` function (lines 33–53).

**`perform_lock()` step 0** (line 71–73) — replace:
```python
# Step 0: ensure container exists, launching on first use.
if not state.launched:
    ensure_container_ready(state, workspace)
```
with:
```python
# Step 0: launch container on first use if not yet provisioned.
if not workshop.environment_exists(state.name, workspace):
    workshop.check_prerequisites()
    workshop.launch(state.name, workspace)
    workshop.verify_exists(state.name, workspace)
    if state.inference is not None:
        workshop.connect(state.name, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF, workspace)
```

**Delete step 4** (lines 91–93): `state.locked = True; state.dump(workspace)`.

**`lock()` idempotency** (line 114): `if state.locked:` → `if is_egress_locked(state.name):`

Add `is_egress_locked` to the lxd import line 27: `from microjail.wrappers.lxd import lock_egress, unlock_egress, is_egress_locked`

### `unlock.py` changes (`src/microjail/commands/unlock.py`)

Line 35: `if not state.locked:` → `if not is_egress_locked(state.name):`

Delete lines 44–48:
```python
state.locked = False
try:
    state.dump(workspace)
except OSError as exc:
    warn(f"Could not update state file after unlock: {exc}")
```

Add `is_egress_locked` to lxd import (line 14): `from microjail.wrappers.lxd import unlock_egress, is_egress_locked`

`State` import may become unused — remove if so.

### `init.py` changes (`src/microjail/commands/init.py`)

**`preflight()` `--force` locked guard** (lines 97–110) — replace entire `if force:` block with:
```python
if force:
    if is_egress_locked(name):
        err(
            f"Environment '{name}' is currently locked. "
            "Run 'microjail unlock' first.",
            code=2,
        )
```
(Remove the `State.from_json` read and try/except — no longer needed.)

**`init()` body** (lines 225–250) — replace `existing_launched` logic:
```python
# OLD:
newly_launched = False
if force:
    state_path = workspace / ".microjail" / "state.json"
    existing_launched = False
    if state_path.exists():
        try:
            existing = State.from_json(workspace)
            existing_launched = existing.launched
        except Exception:
            pass
    if existing_launched:
        ...
        newly_launched = True
```
with:
```python
if force and workshop.environment_exists(name, workspace):
    try:
        workshop.check_prerequisites()
        workshop.refresh(name, workspace)
        workshop.verify_exists(name, workspace)
    except RuntimeError as exc:
        err(str(exc), code=3)
    if config.inference is not None:
        try:
            workshop.connect(name, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF, workspace)
        except RuntimeError as exc:
            err(str(exc), code=3)
```

**State write** (line 252–260): remove `launched=newly_launched` and `locked=False` kwargs.

Add import: `from microjail.wrappers.lxd import is_egress_locked`

### `run.py` changes (`src/microjail/commands/run.py`)

`unlock_after_run(state: State, workspace: Path)` → `unlock_after_run(state: State)` (drop `workspace`).

Delete `state.locked = False; state.dump(workspace)` and the `except OSError` block. Keep only the `unlock_egress` call and its `RuntimeError` handler.

Update both call sites: `unlock_after_run(state, workspace)` → `unlock_after_run(state)`.

### Tests to delete entirely

- `tests/unit/state/test_state_launched_field.py` (5 tests — field gone)
- `tests/unit/state/test_state_locked_field.py` (5 tests — field gone)

### Tests to rewrite (`tests/unit/commands/test_preconditions.py`)

- `test_normal_init_writes_state_with_launched_false` → drop `assert state.launched is False` / `assert state.locked is False`
- `test_force_on_unlaunched_env_writes_files_without_workshop_calls` → mock `workshop.environment_exists` returning `False`; remove `launched=False` state write; drop `assert state.launched is False`
- `test_force_launched_env_calls_refresh_not_launch` → mock `workshop.environment_exists` returning `True`; remove `launched=True` state write; drop `assert state.launched is True`
- `test_force_on_locked_env_exits_2` → patch `microjail.commands.init.is_egress_locked` returning `True`; remove `locked=True` state write
- `test_state_written_with_launched_false_on_normal_init` (parametrised ×2) → drop `assert state.launched is False`

### Tests to rewrite (`tests/unit/commands/test_lock_command.py`)

- `_write_state()` → remove `launched` param
- `test_lock_exits_zero_when_already_locked` → patch `microjail.commands.lock.is_egress_locked` returning `True`; remove `locked=True` state write
- `test_lock_success_updates_state` → rename; remove `assert loaded.locked is True`; patch `microjail.commands.lock.workshop.environment_exists` returning `True`
- `test_lock_gate_failure_triggers_egress_rollback` → remove `assert loaded.locked is False`; patch `workshop.environment_exists` returning `True`
- `test_lock_gate_failure_rollback_survives_unlock_error` → patch `workshop.environment_exists` returning `True`
- **Delete** `test_lock_calls_ensure_container_ready_when_not_launched` — function gone
- **Delete** `test_lock_does_not_call_ensure_container_ready_when_already_launched` — replace with `test_lock_skips_launch_when_container_already_exists` patching `workshop.environment_exists` returning `True`, asserting `workshop.launch` not called
- **Delete** `test_lock_persists_launched_before_lock_egress` — FR-008 moot; replace with `test_lock_launches_when_container_absent` patching `workshop.environment_exists` returning `False`, asserting `workshop.launch` and `workshop.verify_exists` called

### Tests to rewrite (`tests/unit/commands/test_unlock_command.py`)

- `_write_state()` → remove `locked` param
- `test_unlock_exits_zero_when_already_unlocked` → patch `microjail.commands.unlock.is_egress_locked` returning `False`
- `test_unlock_restores_egress_and_updates_state` → patch `is_egress_locked` returning `True`; remove `assert loaded.locked is False`; remove FR-015 `assert loaded.launched is True` assertion (added last turn, now also invalid)
- `test_unlock_exits_nonzero_when_unlock_egress_fails` → patch `is_egress_locked` returning `True`

### Verification commands

```bash
uv run ruff check src/microjail/ tests/unit/
uv run pytest tests/unit/ -v
```

Baseline before change: **141 unit tests passing**.

## Next Steps

1. Edit `src/microjail/state.py` — remove `launched` and `locked` fields + update docstring
2. Edit `src/microjail/wrappers/lxd.py` — add `is_egress_locked` function after `unlock_egress`
3. Edit `src/microjail/commands/lock.py` — delete `ensure_container_ready`, rewrite `perform_lock` step 0, remove step 4, update idempotency guard
4. Edit `src/microjail/commands/unlock.py` — update idempotency guard, remove state mutation
5. Edit `src/microjail/commands/init.py` — replace force-guard, replace force-refresh logic, strip `launched`/`locked` from State constructor
6. Edit `src/microjail/commands/run.py` — simplify `unlock_after_run`
7. Delete `tests/unit/state/test_state_launched_field.py` and `tests/unit/state/test_state_locked_field.py`
8. Rewrite affected tests in `test_preconditions.py`, `test_lock_command.py`, `test_unlock_command.py`
9. Run ruff + pytest; fix any issues
10. Commit on branch `20260605-154611-workshop-init` with `Assisted-By: oh-my-pi (claude-sonnet-4-6; github-copilot)`
