# Research: Thin-Wrapper Init with Lazy Container Launch

**Feature**: `specs/20260605-154611-workshop-init`
**Date**: 2026-06-05

---

## 1. `msgspec.Struct` backward compatibility for `State.launched`

**Decision**: Add `launched: bool = field(default=True)` directly to `State` in `src/microjail/state.py`.

**Why this is backward-compatible**:

- `State.from_json()` is currently a thin `msgspec.json.decode(..., type=cls)` wrapper; there is no custom migration layer.
- The existing `locked` field already proves the pattern: `tests/unit/state/test_state_locked_field.py` removes the `locked` key from an on-disk `state.json`, then `State.from_json()` deserialises successfully and yields `locked=False`.
- `msgspec` uses the declared field default when a field is absent in the incoming JSON. Verified independently with `uv run python` against a minimal `msgspec.Struct`: decoding `{"a": 1}` into a struct with `locked: bool = False` and `launched: bool = True` produced `locked=False, launched=True` with no error.

**Implication**: Existing `state.json` files written before this feature will load as `launched=True`, which is semantically correct because the old `init` path always launched the container before writing state.

**Required follow-through**:

- `microjail init` MUST explicitly write `launched=False`; the field default is only for deserialising old files.
- Add a dedicated `tests/unit/state/test_state_launched_field.py` mirroring the `locked`-field compatibility coverage.

---

## 2. `workshop.ensure_launched` design

**Decision**: Add a wrapper helper in `src/microjail/wrappers/workshop.py`:

```python
def ensure_launched(name: str, project_dir: Path) -> None:
    """Check prerequisites, launch the Workshop environment, then verify it exists."""
```

**Exact behavior**:

1. `check_prerequisites()`
2. `launch(name, project_dir)`
3. `verify_exists(name, project_dir)`

Raise `RuntimeError` from the first failing step; do not catch or translate inside the wrapper.

**Why this helper belongs in `wrappers/workshop.py`**:

- All three operations are Workshop/LXD subprocess concerns.
- The helper has no state-machine policy (`launched`, `locked`, inference) — that belongs in command orchestration.
- `lock` and `run` both need the same launch primitive through `perform_lock()`.

**Do not special-case “already exists” inside `ensure_launched`**:

- The caller should only invoke it when `state.launched is False`.
- Adding an `environment_exists()` pre-check adds a redundant subprocess, introduces TOCTOU risk, and recreates the very Workshop-registry dependency this feature is removing from the normal path.
- If state has drifted to `launched=False` while the container already exists, calling `workshop launch` is the single recovery attempt. If Workshop treats that as a safe no-op, great. If it errors, that error should surface rather than being hidden behind a second policy branch.

---

## 3. `ensure_container_ready` in `commands/lock.py`

**Decision**: Add a command-layer helper in `src/microjail/commands/lock.py`:

```python
def ensure_container_ready(state: State, workspace: Path) -> None:
    """Ensure the container is present/running and inference wiring is ready before lock."""
```

**Call site**: `perform_lock()` should call `ensure_container_ready(state, workspace)` as its first step, before any LXD egress mutation.

**Recommended sequence inside `perform_lock()` after the change**:

1. `ensure_container_ready(state, workspace)`
2. `lock_egress(state.name, workspace)`
3. `run_all_gates(state, workspace)`
4. On gate failure: `unlock_egress(state.name)` rollback
5. On success: `state.locked = True`; `state.dump(workspace)`

**Exact behavior of `ensure_container_ready()`**:

- If `state.launched` is `False`:
  1. `workshop.ensure_launched(state.name, workspace)`
  2. `state.launched = True`
  3. `state.dump(workspace)`
- If `state.launched` is `True`:
  1. Verify the existing container is still running (see §4)
- Then, if `state.inference is not None`:
  1. `workshop.connect(state.name, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF, workspace)`

**State-mutation rule**:

Persist `launched=True` immediately after `workshop.ensure_launched()` succeeds and before *any* later step (`workshop.connect`, `lock_egress`, gates). That is stricter than FR-008 and is the right sequence for two reasons:

- It satisfies FR-008 directly: a crash between launch and `lock_egress` still leaves state truthful.
- It also satisfies the spec’s inference edge case: if `workshop.connect()` fails after a successful lazy launch, the command exits with `launched=true, locked=false`, allowing the next `lock`/`run` to retry connection without re-launching.

**Why `workshop.connect()` should live here, not inside `ensure_launched()`**:

- `ensure_launched()` is a pure Workshop lifecycle primitive.
- Tunnel connection depends on command-layer state (`state.inference`) and must be sequenced relative to state persistence and lock gating.
- The spec requires retrying tunnel connection after a failed first attempt; command-layer orchestration is the right place to own that policy.

---

## 4. External drift detection (`state.launched=True`, container stopped/removed)

**Decision**: Existing gate failure is **not sufficient**. Add an explicit runtime-state check before locking when `state.launched` is already `True`.

**Why the current sequence is insufficient**:

- `perform_lock()` currently calls `lock_egress()` **before** `run_all_gates()`.
- If the container was **removed**, the error surfaces today from the LXD wrapper (`_container_name()` / device queries) before gates run. That part is already adequate.
- If the container was **stopped**, the current gates are not reliable:
  - `check_egress_down()` treats **any non-zero** `lxc exec ... ping` exit as **pass**. A non-running container would also produce a non-zero exit, so this gate cannot distinguish “egress is blocked” from “the container never executed the probe.”
  - `workspace-mounted` and `state-readonly` inspect device config, not process/runtime state; they can still pass on a stopped container.
  - `lock_egress()` mutates LXD config, and config mutation can succeed without proving the container is actually running.

**Recommended helper**: add an explicit LXD runtime check, e.g. in `src/microjail/wrappers/lxd.py`:

```python
def verify_running(env_name: str) -> None:
    """Raise RuntimeError if the Workshop container is missing or not RUNNING."""
```

**Behavior**:

- Resolve the Workshop project + concrete container name.
- Query runtime state (`lxc info` or `lxc list --columns ns`).
- If the container is absent or not `RUNNING`, raise `RuntimeError` with an actionable message naming the recovery path:
  - `workshop start <name>` if it was stopped
  - `microjail init --force` if it was removed or configuration must be re-applied
- Do **not** auto-restart and do **not** fall back to `workshop launch` when `state.launched=True`.

**Call site**: `ensure_container_ready()` should call `verify_running(state.name)` on the `state.launched is True` branch before any `workshop.connect()` or LXD lock mutation.

---

## 5. `init --force` split and the locked-state guard

**Decision**: Branch on **local state**, not Workshop registry.

**Recommended split**:

### A. Write-only path (`launched=False` or no prior state)

Use this branch when:

- there is no `.microjail/state.json`, or
- prior state exists but `launched is False`, or
- prior state exists for a different environment name and this invocation is effectively creating a fresh local config in the workspace.

Behavior:

1. Validate inputs.
2. Check workspace writability.
3. Write config files.
4. Write state with `launched=False, locked=False`.
5. Return success.

No `workshop`/`lxc` subprocess calls in this branch.

### B. Refresh path (`launched=True`)

Use this branch when prior local state exists for the current workspace and indicates the environment has already been launched.

Behavior:

1. Validate inputs.
2. Check workspace writability.
3. Load existing local state.
4. Reject if `existing_state.locked is True`.
5. Write config files.
6. Write state with `launched=True, locked=False`.
7. `workshop.check_prerequisites()`
8. `workshop.refresh(name, workspace)`
9. `workshop.verify_exists(name, workspace)`
10. If inference is configured: `workshop.connect(...)`

**Where the force-on-locked check goes**:

The `locked=True` rejection belongs in **preflight**, immediately after loading the existing state file and **before any file write or Workshop call**. It is a precondition failure (`exit 2`), not a refresh-time runtime error (`exit 3`).

This guard should trigger regardless of whether the user reuses the same name; the workspace currently represents a locked environment and overwriting `.microjail/state.json` under that condition is unsafe.

**Implementation consequence**:

`preflight()` should stop returning `already_exists: bool`. The useful return value after this refactor is the previously loaded `State | None` (or an equivalent small enum/record carrying `launched` + `locked`).

---

## 6. Remove `launch_and_verify()` from `init.py`

**Decision**: Delete `launch_and_verify()` outright. Do not replace it with another generic helper.

**What replaces it**:

- Lazy launch uses the new wrapper helper: `workshop.ensure_launched()` from `perform_lock()` / `run()`.
- `init --force` on a launched environment uses **inline wrapper calls** in the launched branch of `init()`:
  1. `workshop.check_prerequisites()`
  2. `workshop.refresh()`
  3. `workshop.verify_exists()`
  4. optional `workshop.connect()`

**Why inline here is better than another wrapper helper**:

- There is only one refresh call site.
- The branch decision depends on local-state policy (`launched`, `locked`, workspace semantics), which belongs in the command module.
- A new `refresh_and_verify()` helper would buy almost nothing and would blur the intended boundary: wrappers own subprocess primitives; commands own lifecycle policy.

---

## 7. `tests/unit/commands/test_preconditions.py` update strategy

**Decision**: Rewrite the tests to assert local-state-driven behavior instead of Workshop-registry-driven behavior.

### Direct replacements for the four known breakages

1. **`test_new_env_calls_launch_not_refresh`**
   - **Replace with**: `test_normal_init_writes_state_with_launched_false_and_never_calls_launch_or_refresh`
   - **Assertion**: normal `init` succeeds, writes `.microjail/state.json` with `launched=False`, and calls neither `workshop.launch()` nor `workshop.refresh()`.

2. **`test_force_calls_refresh_not_launch_when_env_exists`**
   - **Replace with**: `test_force_on_local_launched_state_calls_refresh_verify_and_not_launch`
   - **Setup**: create an existing local `state.json` with `launched=True, locked=False`.
   - **Assertion**: `init --force` calls `workshop.refresh()` then `workshop.verify_exists()`, does not call `workshop.launch()`, and preserves `launched=True` in the rewritten state.

3. **`test_state_not_written_when_creation_fails`**
   - **Delete the old invariant**: there is no normal-path “creation” step anymore.
   - **Replace with two smaller assertions**:
     - `test_normal_init_writes_state_with_launched_false`
     - `test_force_refresh_failure_leaves_rewritten_state_file_present`
   - **Rationale**: after this refactor, local config/state are written independently of container provisioning. The old “no state unless launch succeeds” contract is gone.

4. **`test_writable_workspace_proceeds`**
   - **Replace with**: `test_writable_workspace_proceeds_to_local_state_duplicate_check`
   - **Setup**: writable workspace + pre-existing `.microjail/state.json`.
   - **Assertion**: the command fails with the duplicate-state “already exists” message, not with a writability error.

### One additional test in the same file that also needs adjustment

The current `test_non_writable_workspace_no_workshop_call` expects `workshop.check_prerequisites()` to run once. That expectation must be removed. After this feature, the correct assertion is that **no** Workshop wrapper (`check_prerequisites`, `environment_exists`, `launch`, `refresh`, `verify_exists`, `connect`) is called on the non-writable path.

---

## 8. New unit tests required

### A. `tests/unit/state/test_state_launched_field.py`

Add a dedicated file for `launched` compatibility coverage. The six useful tests are:

1. `test_launched_field_defaults_to_true`
2. `test_launched_field_round_trip_false`
3. `test_launched_field_round_trip_true`
4. `test_launched_field_persisted_in_json_false`
5. `test_launched_field_persisted_in_json_true`
6. `test_launched_field_absent_in_old_state_file_defaults_to_true`

That is the same compatibility story as `locked`, with the one important difference that both persisted values matter because `init` will intentionally write `false` while the deserialisation default remains `true`.

### B. `tests/unit/commands/test_lock_command.py`

Add three lazy-launch-focused tests:

1. **Lazy launch before lock**
   - Initial state: `launched=False, locked=False`
   - Assert ordered behavior: `workshop.ensure_launched()` happens before `lock_egress()`, `state.launched` is persisted before `lock_egress()`, then normal gate execution proceeds and final state is `launched=True, locked=True`.

2. **Inference connect is sequenced before egress mutation**
   - Initial state: `launched=False, locked=False, inference="llama-cpp"`
   - Assert order: `ensure_launched()` → `state.dump(launched=True)` → `workshop.connect(...)` → `lock_egress()`.
   - This is the FR-009 / FR-008 interaction test.

3. **Already-launched state skips relaunch**
   - Initial state: `launched=True, locked=False`
   - Assert `workshop.ensure_launched()` is **not** called and the command proceeds straight to runtime verification / optional connect / lock logic.

### C. `tests/unit/commands/test_preconditions.py`

Add three init-behavior tests that did not exist before:

1. `test_normal_init_does_not_call_check_prerequisites_or_environment_exists`
   - Verifies the normal path is a pure file-write path.

2. `test_second_init_is_rejected_by_local_state_file_not_workshop_registry`
   - Creates `.microjail/state.json`, invokes `init` again, and asserts the duplicate rejection happens without consulting Workshop.

3. `test_force_locked_state_exits_2_without_any_workshop_call`
   - Creates prior state with `launched=True, locked=True`, invokes `init --force`, and asserts the command rejects with an unlock instruction before any write/refresh/connect attempt.

---

## Summary of concrete decisions

| Topic | Decision |
|---|---|
| `State.launched` compatibility | Use `field(default=True)`; old files without the key decode as `launched=True` |
| Lazy launch primitive | Add `workshop.ensure_launched(name, project_dir)` = prerequisites + launch + verify |
| Lock precondition helper | Add `ensure_container_ready(state, workspace)` in `commands/lock.py` |
| `launched=True` drift | Add explicit runtime-state check; current gates are insufficient for stopped containers |
| `init --force` branching | Use local `state.json` (`launched`, `locked`) rather than `workshop.environment_exists()` |
| Locked force guard | Reject in preflight, before any file write or Workshop call |
| `launch_and_verify()` | Delete; lazy launch uses wrapper helper, refresh path uses inline wrapper calls |
| Test strategy | Replace Workshop-registry assertions with local-state assertions; add launched-field + lazy-launch coverage |
