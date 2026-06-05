---

description: "Task list for simplify-exception-handling refactor"
---

# Tasks: Simplify Exception Handling

**Input**: Design documents from `specs/20260605-095056-simplify-exception-handling/`

**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓

**Tests**: Not requested — existing `pytest tests/unit/` suite is the verification mechanism.

**Organization**: Tasks grouped by user story. US1 (CTF ExitStack) and US2 (`write_config_files`) are fully independent and can begin immediately after Phase 1. US3 (gates) depends on T002; US4 (commands) depends on T003.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US4 from spec.md)

---

## Phase 1: Setup

**Purpose**: Establish a clean baseline before any edits.

- [x] T001 Run `pytest tests/unit/ -x -q` from the project root and confirm zero failures; record the count of passing tests as the baseline to verify against in Phase 7

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add the two shared helpers that US3 and US4 both depend on. US1 and US2 can start in parallel with this phase.

**⚠️ CRITICAL**: US3 cannot begin until T002 is complete; US4 cannot begin until T003 is complete.

- [x] T002 [P] Add `resolve_project(gate_name: str) -> tuple[str | None, GateResult | None]` to `src/microjail/gates/__init__.py`. Implementation: call `_workshop_project()` (imported from `microjail.wrappers.lxd` — add to `TYPE_CHECKING` block or import inside the function); return `(_workshop_project(), None)` on success; catch `RuntimeError as exc` and return `(None, GateResult(name=gate_name, passed=False, message=f"Cannot determine LXD project to run {gate_name} check: {exc}. Ensure Workshop and LXD are running."))`. Place after the `GateResult` dataclass definition. Full signature: `def resolve_project(gate_name: str) -> tuple[str | None, GateResult | None]:`
- [x] T003 [P] Add `load_state_or_exit(workspace: Path) -> State` to `src/microjail/commands/__init__.py`. Implementation: replace the bare docstring with imports and the helper. Imports needed: `from pathlib import Path`, `from microjail.output import err`, `from microjail.state import State`. Body: call `State.from_json(workspace)` inside a `try`; catch `FileNotFoundError` → `err("No microjail environment found in the current directory. Run 'microjail init' first.")`; catch `RuntimeError as exc` → `err(str(exc))`; return the loaded state on success. Full signature: `def load_state_or_exit(workspace: Path) -> State:`

**Checkpoint**: Helpers committed. US3 and US4 may now begin. US1 and US2 may have been running in parallel already.

---

## Phase 3: User Story 1 — CTF Runner ExitStack Cleanup (Priority: P1) 🎯 MVP

**Goal**: Replace the nested `try/except` blocks and `if x is not None` guards in the `finally` clause of `ctf/main.py:run()` with an `ExitStack` whose callbacks are registered at resource acquisition.

**Independent Test**: Run `pytest tests/unit/ctf/test_ctf_main.py -v` — all tests must pass. The `patched_env` fixture patches all external calls, so cleanup path is exercised on every test invocation.

### Implementation for User Story 1

- [x] T004 [US1] Add four private cleanup-callback helpers immediately before `run()` in `ctf/main.py`:

  ```python
  def terminate_proc(proc: subprocess.Popen[bytes]) -> None:
      with contextlib.suppress(Exception):
          proc.terminate()
          proc.wait(timeout=10)

  def shutdown_server(server: HostHttpServer) -> None:
      with contextlib.suppress(Exception):
          server.server.shutdown()

  def cleanup_egress(console: Console, env_name: str) -> None:
      try:
          unlock_egress(env_name)
      except Exception as exc:
          console.print(f"[yellow]Warning: unlock_egress failed: {exc}[/yellow]")

  def cleanup_env(console: Console, env_name: str, workspace: Path) -> None:
      try:
          workshop_client.remove(env_name, workspace)
      except Exception as exc:
          console.print(f"[yellow]Warning: workshop remove failed: {exc}[/yellow]")
  ```

  `Path` is already imported; `Console`, `unlock_egress`, `workshop_client` are already imported. Verify `HostHttpServer` is importable from `ctf.http_server` (already imported).

- [x] T005 [US1] In `ctf/main.py:run()`, remove the seven null-sentinel variable declarations below the argument-validation block:

  ```python
  # DELETE these six lines:
  server: HostHttpServer | None = None
  tmp_secret_path: Path | None = None
  workspace: Path | None = None
  env_name: str | None = None
  proc: subprocess.Popen[bytes] | None = None
  ```

  Keep `outcome: Literal["pass", "fail", "error", "inconclusive"] | None = None`, `run_obj: TestRun | None = None`, and `shutdown = threading.Event()` — those are still referenced after the `with` block. Add `proc: subprocess.Popen[bytes] | None = None` back just before the `try:` since it is checked in the `except Exception` handler (`outcome = "inconclusive" if proc is None else "error"`).

- [x] T006 [US1] In `ctf/main.py:run()`, wrap the entire body of the existing `try:` block (lines ~201–353, i.e. Phase 1 setup through Phase 3 monitor loop including `run_obj.outcome = outcome` and `run_obj.finished_at = datetime.now(UTC)`) in `with contextlib.ExitStack() as stack:`. Register each resource callback immediately after its acquisition:

  1. After `workspace = Path(tempfile.mkdtemp(...))`:
     `stack.callback(shutil.rmtree, workspace, ignore_errors=True)`
  2. After `workshop_client.launch(env_name, workspace)` and `workshop_client.verify_exists(...)`,
     register in this order so LIFO cleanup calls unlock BEFORE remove:
     ```python
     stack.callback(cleanup_env, console, env_name, workspace)   # runs 2nd-to-last
     stack.callback(cleanup_egress, console, env_name)            # runs before remove
     ```
  3. After `tmp_secret_path = Path(f"/tmp/ctf-secret-{uuid.uuid4().hex}")`:
     `stack.callback(tmp_secret_path.unlink, missing_ok=True)`
  4. After `server = start_http_server(net_secret.value, port=port)`:
     `stack.callback(shutdown_server, server)`
  5. After `proc = subprocess.Popen(...)`:
     `stack.callback(terminate_proc, proc)`

  The existing outer `try:` becomes `try:` wrapping only `with contextlib.ExitStack() as stack:`.

- [x] T007 [US1] In `ctf/main.py:run()`, remove the entire `finally:` block (Phase 4 cleanup, currently lines ~361–390). The ExitStack registered in T006 now handles all cleanup when the `with` block exits — whether normally, via exception, or via signal-driven shutdown. Verify nothing in the removed `finally` block is non-cleanup logic (outcome-setting belongs in `except`; report generation is after the try/except).

**Checkpoint**: Run `pytest tests/unit/ctf/test_ctf_main.py -v` — all tests must pass before proceeding.

---

## Phase 4: User Story 2 — `write_config_files` Single OSError Guard (Priority: P2)

**Goal**: Replace the three structurally identical `try/except OSError → err(code=3)` blocks in `write_config_files` with a single `try` block.

**Independent Test**: Run `pytest tests/unit/commands/test_preconditions.py -v` — all tests must pass.

### Implementation for User Story 2

- [x] T008 [US2] In `src/microjail/commands/init.py:write_config_files()`, replace the three separate `try/except OSError` blocks (covering the `.yaml` write, the SDK `sdk.yaml` write, and the `opencode.jsonc` write) with a single `try:` that wraps all three write operations, with a single `except OSError as exc: err(f"Cannot write to current directory: {exc}", code=3)` handler at the end. The three conditional guards (`if config.inference is not None:`, `if agent == "opencode":`) stay inside the `try` block as-is. The resulting structure:

  ```python
  def write_config_files(...) -> None:
      workshop_def_path = workspace / ".workshop" / f"{name}.yaml"
      try:
          workshop_def_path.parent.mkdir(parents=True, exist_ok=True)
          workshop_def_path.write_text(generate_workshop_yaml(config))
          if config.inference is not None:
              sdk_dir = workspace / ".workshop" / "local-inference"
              sdk_dir.mkdir(parents=True, exist_ok=True)
              (sdk_dir / "sdk.yaml").write_text(generate_sdk_yaml(config))
          if agent == "opencode":
              (workspace / "opencode.jsonc").write_text(
                  generate_opencode_config(socket_url)
              )
      except OSError as exc:
          err(f"Cannot write to current directory: {exc}", code=3)
  ```

**Checkpoint**: Run `pytest tests/unit/commands/test_preconditions.py -v` — all tests must pass.

---

## Phase 5: User Story 3 — Gate Files Use Shared `resolve_project` Helper (Priority: P3)

**Goal**: Replace the three identical `try/except RuntimeError` guards around `_workshop_project()` in the gate files with calls to `resolve_project` from `gates/__init__.py`. **Scope note**: `inference_tunnel.py` is excluded — it does not call `_workshop_project()` and is therefore out of scope for FR-005.

**Depends on**: T002 (foundational)

**Independent Test**: Run `pytest tests/unit/gates/ -v` — all tests must pass.

### Implementation for User Story 3

- [x] T009 [P] [US3] In `src/microjail/gates/egress.py:check_egress_down()`, replace:
  ```python
  try:
      project = _workshop_project()
  except RuntimeError as exc:
      return GateResult(
          name="egress-down",
          passed=False,
          message=(...),
      )
  ```
  with:
  ```python
  project, err_result = resolve_project("egress-down")
  if err_result is not None:
      return err_result
  ```
  Add `from microjail.gates import resolve_project` (or use a relative import). Remove the `_workshop_project` import if no longer needed directly. Verify `project` is typed as `str` after the guard.

- [x] T010 [P] [US3] In `src/microjail/gates/state_readonly.py:check_state_readonly()`, apply the same replacement as T009 using gate name `"state-readonly"`. Remove the `_workshop_project` import if no longer needed directly.

- [x] T011 [P] [US3] In `src/microjail/gates/workspace.py:check_workspace_mounted()`, apply the same replacement as T009 using gate name `"workspace-mounted"`. Remove the `_workshop_project` import if no longer needed directly.

**Checkpoint**: Run `pytest tests/unit/gates/ -v` — all tests must pass.

---

## Phase 6: User Story 4 — Command Entry Points Use Shared `load_state_or_exit` Helper (Priority: P4)

**Goal**: Replace the identical `try/except FileNotFoundError/RuntimeError → err()` boilerplate at the top of `lock()`, `unlock()`, and `run()` with a call to `load_state_or_exit`. Consolidate `unlock_after_run` to a single `try` with two `except` clauses.

**Depends on**: T003 (foundational)

**Independent Test**: Run `pytest tests/unit/commands/ -v` — all tests must pass.

### Implementation for User Story 4

- [x] T012 [P] [US4] In `src/microjail/commands/lock.py:lock()`:

  **Step 1 (pre-edit verification)**: Read `tests/unit/commands/test_lock_command.py` and note any assertions on the `RuntimeError` / gate-failure path (exit code, output text). This determines whether a test assertion update is needed under FR-007.

  Replace the state-loading boilerplate:
  ```python
  try:
      state = State.from_json(workspace)
      if state.locked:
          ...
          return
      perform_lock(state, workspace)
  except FileNotFoundError:
      err("No microjail environment found...")
  except RuntimeError as exc:
      err(str(exc))
  ```
  with:
  ```python
  state = load_state_or_exit(workspace)
  if state.locked:
      typer.echo(f"Environment '{state.name}' is already locked.")
      return
  try:
      perform_lock(state, workspace)
  except RuntimeError as exc:
      err(str(exc))
  ```
  The `FileNotFoundError`/`RuntimeError` wrapper around `State.from_json` is replaced by `load_state_or_exit`. The `except RuntimeError` around `perform_lock` is **kept** as a narrow guard — `perform_lock` raises `RuntimeError` when a gate fails and that error must be routed through `err()` (constitution §V: error paths must produce a user-actionable message with the correct exit code). Add `from microjail.commands import load_state_or_exit`. Remove `State` import if no longer needed directly.

- [x] T013 [P] [US4] In `src/microjail/commands/unlock.py:unlock()`:

  **Note**: `unlock_egress(state.name)` is currently **inside** the big `try:` block (lines ~33–46) and its `RuntimeError` is caught by `except RuntimeError as exc: err(str(exc))`. After extracting state-loading, the unlock call needs its own narrow guard (constitution §V).

  Replace:
  ```python
  try:
      state = State.from_json(workspace)
      if not state.locked:
          ...
          return
      unlock_egress(state.name)
  except FileNotFoundError:
      err("No microjail environment found...")
  except RuntimeError as exc:
      err(str(exc))
  ```
  with:
  ```python
  state = load_state_or_exit(workspace)
  if not state.locked:
      typer.echo(f"Environment '{state.name}' is already unlocked.")
      return
  try:
      unlock_egress(state.name)
  except RuntimeError as exc:
      err(str(exc))
  ```
  The `except RuntimeError` around `unlock_egress` is **kept** — it was previously inside the big try block and must remain handled to satisfy constitution §V. Add `from microjail.commands import load_state_or_exit`. Remove `State` import if no longer needed.

- [x] T014 [US4] In `src/microjail/commands/run.py:run()`, replace the `try/except FileNotFoundError/RuntimeError` block:
  ```python
  state = load_state_or_exit(workspace)
  try:
      perform_lock(state, workspace)
  except RuntimeError as exc:
      err(str(exc))
  ```
  The `except RuntimeError` around `perform_lock` is **kept** for the same reason as T012 (constitution §V). Then in `unlock_after_run`, consolidate the two sequential `try/except` blocks into a single `try` with two `except` clauses:
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
  Add `from microjail.commands import load_state_or_exit`. Remove `State` import if no longer used in the module directly.

**Checkpoint**: Run `pytest tests/unit/commands/ -v` — all tests must pass.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Confirm ruff is clean on all changed files; confirm full test suite passes.

- [x] T015 [P] Run `ruff check ctf/main.py src/microjail/gates/__init__.py src/microjail/gates/egress.py src/microjail/gates/state_readonly.py src/microjail/gates/workspace.py src/microjail/commands/__init__.py src/microjail/commands/init.py src/microjail/commands/lock.py src/microjail/commands/unlock.py src/microjail/commands/run.py` and fix any diagnostics. Common issues to expect: unused imports (`_workshop_project` in gate files, `State` in command files), missing type annotation on new helpers.
- [x] T016 Run `pytest tests/unit/ -v` from the project root and confirm zero test failures (no regressions, no tests deleted or skipped that were passing before).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — T002 and T003 run in parallel
- **Phase 3 (US1)**: Independent of Foundational — can begin after Phase 1 in parallel with Phase 2
- **Phase 4 (US2)**: Independent of Foundational — can begin after Phase 1 in parallel with Phases 2 and 3
- **Phase 5 (US3)**: Depends on T002 only
- **Phase 6 (US4)**: Depends on T003 only
- **Phase 7 (Polish)**: Depends on all preceding phases

### User Story Dependencies

- **US1 (P1)**: No dependency on Foundational. Start immediately after T001.
- **US2 (P2)**: No dependency on Foundational. Start immediately after T001. Can run alongside US1.
- **US3 (P3)**: Depends on T002 (`resolve_project` helper). Can run in parallel with US1/US2 once T002 is done.
- **US4 (P4)**: Depends on T003 (`load_state_or_exit` helper). Can run in parallel with US1/US2/US3 once T003 is done.

### Within Each User Story

- US1: T004 → T005 → T006 → T007 (sequential, all touch `ctf/main.py`)
- US2: T008 (single task)
- US3: T009, T010, T011 (parallel — different files)
- US4: T012, T013 (parallel) → T014 (sequential — `run.py` only, but can overlap with T012/T013)

### Parallel Opportunities

- T002 and T003 (Foundational helpers) run in parallel
- US1 and US2 can run concurrently with Foundational (different files)
- T009, T010, T011 (US3 gates) run in parallel
- T012 and T013 (US4 lock/unlock) run in parallel
- T015 and T016 (Polish) run in parallel

---

## Parallel Example: US3 Gates

```
# After T002 completes, launch all three gate updates simultaneously:
Task: "Update egress.py to use resolve_project (T009)"     → src/microjail/gates/egress.py
Task: "Update state_readonly.py to use resolve_project (T010)" → src/microjail/gates/state_readonly.py
Task: "Update workspace.py to use resolve_project (T011)"  → src/microjail/gates/workspace.py
```

## Parallel Example: Phases 2–4 (maximum parallelism after T001)

```
Thread A: T002 (gates helper) → T009 → T010 → T011
Thread B: T003 (commands helper) → T012 → T013 → T014
Thread C: T004 → T005 → T006 → T007 (US1 ExitStack)
Thread D: T008 (US2 write_config_files)
# All threads converge at Phase 7: T015 (ruff) + T016 (pytest)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: T001 (baseline)
2. Complete Phase 3: T004–T007 (CTF ExitStack — independent of foundational)
3. **STOP and VALIDATE**: `pytest tests/unit/ctf/test_ctf_main.py -v`
4. The most structurally significant cleanup path is refactored; remaining stories are mechanical deduplication

### Incremental Delivery

1. T001 → baseline established
2. T004–T008 (parallel) → US1 + US2 complete; riskiest change done
3. T002–T003 (parallel) → helpers ready
4. T009–T011 (parallel) → US3 complete
5. T012–T014 (parallel) → US4 complete
6. T015–T016 → full verification

### Parallel Team Strategy

With two engineers:

1. Both run T001 together
2. Engineer A: T002 → T009 → T010 → T011 (gates chain)
3. Engineer B: T003 → T012 → T013 → T014 (commands chain)
4. Both can work US1 (T004–T007) and US2 (T008) simultaneously if desired since those touch `ctf/main.py` and `commands/init.py` respectively

---

## Notes

- `[P]` tasks touch different files and have no incomplete dependencies — safe to run concurrently
- The `[Story]` label maps each task to the user story it delivers
- `perform_lock` in `lock.py` and `run.py`, and `unlock_egress` in `unlock.py`, each retain a narrow `try/except RuntimeError: err(str(exc))` guard (constitution §V — see T012, T013, T014). Only the `State.from_json` boilerplate is moved to `load_state_or_exit`.
- For T012/T013/T014: if any existing test mocks `State.from_json` to raise, those tests will now exercise `load_state_or_exit` — their assertions should still pass since the exit code and message are identical
- Commit after each checkpoint (end of each phase) to isolate blame if a regression is introduced
