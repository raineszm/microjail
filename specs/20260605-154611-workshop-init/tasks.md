# Tasks: Thin-Wrapper Init with Lazy Container Launch

**Input**: Design documents from `specs/20260605-154611-workshop-init/`

**Prerequisites**: [plan.md](./plan.md) ✓, [spec.md](./spec.md) ✓, [research.md](./research.md) ✓, [data-model.md](./data-model.md) ✓, [contracts/cli-commands.md](./contracts/cli-commands.md) ✓

**Tests**: Included — the constitution requires regression coverage for all lock/unlock path changes and the spec includes measurable test-coverage success criteria (SC-002, SC-004, SC-006).

**Organization**: Tasks are grouped by user story. US1 (thin init) and US2 (lazy launch) are both P1 but sequential: US2's `perform_lock` change depends on the `launched` field from the Foundational phase, and US1 and US2 touch disjoint source files so they can be parallelized at the source level.

---

## Phase 1: Foundational — `State.launched` field

**Purpose**: Add the `launched` field to `State`. Every downstream change reads or writes this field; nothing else can land until this is present and tested.

**⚠️ CRITICAL**: No US1/US2/US3/US4 work can begin until this phase is complete.

- [X] T001 Add `launched: bool = field(default=True)` to `State` in `src/microjail/state.py`, positioned between `socket_url` and `locked`; update the class docstring to describe the new field and all three valid lifecycle combinations (`{launched=False,locked=False}`, `{launched=True,locked=False}`, `{launched=True,locked=True}`)
- [X] T002 [P] Write `tests/unit/state/test_state_launched_field.py` with 5 tests mirroring `test_state_locked_field.py`: `test_launched_field_defaults_to_true`, `test_launched_field_round_trip_false`, `test_launched_field_round_trip_true`, `test_launched_field_persisted_in_json`, `test_launched_field_absent_in_old_state_file_defaults_to_true`

**Checkpoint**: `uv run pytest tests/unit/state/` passes. `launched` field present and backward-compatible.

---

## Phase 2: US1 + US4 — Thin init (no subprocess calls on normal path)

**Goal**: `microjail init` writes config files and state (`launched=False`) and exits. Zero calls to `workshop` or `lxc` on the normal path. US4 structural simplicity is achieved as a direct consequence.

**Independent Test**: Run `microjail init <name>` in a temp workspace; assert exit 0, `.workshop/<name>.yaml` exists, `.microjail/state.json` exists with `launched=false, locked=false`; assert `workshop info <name>` exits non-zero (no container). Verify zero Workshop/lxc subprocess calls via unit test mocks (SC-002).

### Implementation for US1 + US4

- [X] T003 [US1] Restructure `preflight()` in `src/microjail/commands/init.py`: (a) remove the `workshop.check_prerequisites()` call; (b) remove the `workshop.environment_exists()` call and the `already_exists` return value; (c) change duplicate detection to check for `.microjail/state.json` presence rather than Workshop env existence; (d) add FR-017 guard: when `--force` and existing state has `locked=True`, call `err("Environment '<name>' is currently locked. Run 'microjail unlock' first.", code=2)`; (e) change return type annotation from `bool` to `None`
- [X] T004 [US1] Rewrite `init()` body in `src/microjail/commands/init.py`: (a) delete the call to `launch_and_verify()` from the normal path; (b) delete the `workshop.connect()` call from the normal path; (c) add `--force`+`launched=False` branch (overwrite files, write `State(launched=False)`, no Workshop call); (d) add `--force`+`launched=True, locked=False` branch (overwrite files, call `workshop.check_prerequisites()` → `workshop.refresh()` → `workshop.verify_exists()` → `workshop.connect()` if inference, write `State(launched=True)`); (e) on the normal path, construct `State(..., launched=False)` explicitly; (f) call `state.dump(workspace)` as the last step before the success echo
- [X] T005 [US1] Delete `launch_and_verify()` function entirely from `src/microjail/commands/init.py`; update the module docstring at the top of the file to reflect the new 6-step orchestration order (validate → preflight → build config → write files → write state → echo) replacing the old 8-step sequence

### Tests for US1 + US4

- [X] T006 [P] [US1] Update `tests/unit/commands/test_preconditions.py`: (a) delete `test_new_env_calls_launch_not_refresh` and replace with `test_normal_init_makes_no_workshop_calls` (mock all workshop functions, assert zero calls to `launch`, `refresh`, `verify_exists`, `connect`, `check_prerequisites`); (b) delete `test_force_calls_refresh_not_launch_when_env_exists` and replace with `test_force_launched_env_calls_refresh_not_launch` (write state with `launched=True, locked=False`, mock workshop, assert `refresh` + `verify_exists` called; `launch` not called); (c) delete `test_state_not_written_when_creation_fails` and replace with `test_state_written_with_launched_false_on_normal_init` (normal init writes state with `launched=False` regardless of workshop availability); (d) update `test_writable_workspace_proceeds` to remove expectation of `check_prerequisites` call; (e) add `test_force_on_locked_env_exits_2` (write state with `launched=True, locked=True`; assert exit 2 and "unlock" in output; assert zero Workshop calls); (f) add `test_force_on_unlaunched_env_writes_files_without_workshop_calls` (write state with `launched=False`; `init --force`; assert exit 0, zero Workshop calls, state rewritten with `launched=False`)

**Checkpoint**: `uv run pytest tests/unit/commands/test_preconditions.py tests/unit/state/` passes; `ruff check src/microjail/commands/init.py` clean; `microjail init --help` still works.

---

## Phase 3: US2 — Lazy container launch on `lock` and `run`

**Goal**: `microjail lock` and `microjail run` provision the container on first use (when `state.launched=False`). The `launched=True` persists before any LXD mutation (FR-008). Inference tunnel is connected before `lock_egress` when `state.inference` is set.

**Independent Test**: Run `microjail init <name>` only (no lock/run); assert `workshop info` exits non-zero; run `microjail lock`; assert exit 0, `workshop info` exits 0, `state.launched=True, state.locked=True`. Then `microjail unlock`; assert `state.launched=True, state.locked=False`.

### Implementation for US2

- [X] T007 [US2] Add `ensure_launched(name: str, project_dir: Path) -> None` to `src/microjail/wrappers/workshop.py`: calls `check_prerequisites()`, then `launch(name, project_dir)`, then `verify_exists(name, project_dir)`; raise `RuntimeError` on any failure; add full docstring explaining that the caller must persist `state.launched=True` after this returns
- [X] T008 [P] [US2] Add `ensure_container_ready(state: State, workspace: Path) -> None` to `src/microjail/commands/lock.py`: (a) call `workshop.ensure_launched(state.name, workspace)`; (b) set `state.launched = True`; (c) call `state.dump(workspace)` (FR-008: persist before any LXD call); (d) if `state.inference is not None`, import `INFERENCE_PLUG_REF`, `INFERENCE_SLOT_REF` from `microjail.config.workshop` and call `workshop.connect(state.name, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF, workspace)`; add full docstring explaining FR-008 sequencing
- [X] T009 [US2] Update `perform_lock()` in `src/microjail/commands/lock.py`: insert as the new first statement — `if not state.launched: ensure_container_ready(state, workspace)` — labelled as "# Step 0 (new): ensure container exists, launching on first use"; update the function docstring to describe the new Step 0 and its failure semantics (`launched` stays `False` on failure, `locked` stays `False`)

### Tests for US2

- [X] T010 [P] [US2] Add 3 lazy-launch unit tests to `tests/unit/commands/test_lock_command.py`: (a) `test_lock_calls_ensure_container_ready_when_not_launched` — write state with `launched=False`, mock `ensure_container_ready`, assert it is called; (b) `test_lock_does_not_call_ensure_container_ready_when_already_launched` — write state with `launched=True`, assert `ensure_container_ready` not called; (c) `test_lock_persists_launched_before_lock_egress` — mock `ensure_launched` and `lock_egress`; use side-effect ordering to assert `state.dump()` (with `launched=True`) is called before `lock_egress`, satisfying FR-008
- [X] T011 [P] [US2] Update `lxd_environment` fixture in `tests/integration/commands/conftest.py`: after `microjail init`, call `microjail lock` (which triggers lazy launch, persists `launched=True`, and then unlocks to leave `locked=False`) rather than calling `workshop launch` directly — this ensures both the container and `state.json` reflect `launched=True, locked=False`; update `us1_env` and `us2_env` fixtures in `tests/integration/commands/test_init_command.py` the same way; if `microjail lock` is undesirable for fixture teardown reasons, call `wrappers.workshop.launch()` + `wrappers.workshop.verify_exists()` directly and then write `state.launched=True` to the state file before yielding
- [X] T012 [P] [US2] Update `tests/integration/commands/test_init_command.py`: (a) replace `test_us1_workshop_env_exists` and `test_us2_workshop_env_exists` with negated versions asserting `workshop info <name>` exits non-zero immediately after init; (b) add `test_us1_workshop_env_exists_after_lock` and `test_us2_workshop_env_exists_after_lock` that call `microjail lock` after init and then assert `workshop info` exits 0; (c) update `test_force_reinit_env_still_exists` to explicitly launch the env before calling `--force`
- [X] T020 [P] [US2] Add `test_run_lazy_launches_unlaunched_environment_and_unlocks_after_success` to `tests/integration/commands/test_run_command.py`: run `microjail init <name>` only, assert `workshop info` non-zero, run `microjail run -- echo hello`, assert exit 0, assert `workshop info` exits 0 (container created), assert `state.launched=true, state.locked=false` (run cleaned up correctly) — covers SC-004 `run` path

**Checkpoint**: `uv run pytest tests/unit/commands/test_lock_command.py` passes; integration test fixtures updated; T020 test added.

---

## Phase 4: US3 — `--force` for both lifecycle states (P2)

US3's source-code changes are delivered in T003–T005 (Phase 2). This phase validates them with targeted integration tests.

**Goal**: `--force` on an unconfigured workspace (no state) works; `--force` on `launched=False` overwrites files without Workshop calls; `--force` on `launched=True, locked=False` refreshes the live container; `--force` on `launched=True, locked=True` exits 2.

**Independent Test**: (a) `init`, then `init --force --inference llama-cpp --agent opencode`; assert files updated, `workshop info` still non-zero. (b) `init` + `lock` (triggers launch), then `init --force`; assert exit 0, `workshop refresh` was called, env still present.

### Tests for US3

- [X] T013 [P] [US3] Add to `tests/integration/commands/test_init_command.py`: `test_force_reinit_unlaunched_env_rewrites_files_without_launching` — run bare `init`, assert `workshop info` non-zero, run `init <name> --force --inference llama-cpp --agent opencode`, assert exit 0, assert `workshop info` still non-zero, assert `.workshop/<name>.yaml` now contains inference config, assert `opencode.jsonc` exists, assert state has `inference='llama-cpp'` and `launched=false`
- [X] T014 [P] [US3] Add to `tests/integration/commands/test_init_command.py`: `test_force_on_locked_env_exits_2_integration` — run `init`, run `microjail lock` (triggers lazy launch), run `init <name> --force`, assert exit 2 and "unlock" in output, assert state still has `locked=true`; also add `test_duplicate_name_rejected_when_only_local_files_exist` — run `init`, assert `workshop info` non-zero, run `init <same-name>` again, assert exit 2 and "already exists" in output

**Checkpoint**: Integration tests for US3 pass with `--run-long`; `ruff check src/microjail/` clean.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Docstring accuracy, ruff compliance, and constitution audit trail.

- [X] T015 [P] Update the module-level docstring in `src/microjail/commands/init.py` to document the `--force`+`launched=True` path in the orchestration comment (the step-by-step sequence in the module docstring already updated by T005 only covers the normal path; add a separate `--force` flow note describing the extra check_prerequisites → refresh → verify_exists → connect steps)
- [X] T016 [P] Update the module-level docstring in `src/microjail/commands/lock.py` (the module overview) and the `lock()` function docstring to mention that first-time invocation provisions the container on demand; do NOT re-edit the `perform_lock()` docstring — that is covered by T009
- [X] T017 [P] Run `ruff check --fix src/microjail/state.py src/microjail/commands/init.py src/microjail/commands/lock.py src/microjail/wrappers/workshop.py` and fix any remaining diagnostics without `# noqa` suppressions (constitution §IV)
- [X] T018 Run `uv run pytest tests/unit/` to confirm all unit tests pass; also add a 1-line assertion to `tests/unit/commands/test_unlock_command.py` verifying that `state.launched` is unchanged after `unlock` (FR-015 traceability — `unlock` is not otherwise modified, so this is a read-only assertion on the existing state round-trip)
- [X] T019 Run `uv run pytest tests/integration/ --run-long` after all fixture and integration test updates (T011–T014) to confirm SC-003; note: requires a live Workshop + LXD environment; skip if running in a CI environment without LXD and document the gap explicitly in the PR description
---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — start immediately
- **US1+US4 (Phase 2)**: Depends on Phase 1 (reads/writes `state.launched`); can start in parallel with US2 source work since they touch disjoint files
- **US2 (Phase 3)**: Depends on Phase 1 (`state.launched` field must exist); source work (T007–T009) is independent of Phase 2 and can proceed in parallel
- **US3 (Phase 4)**: Depends on Phase 2 (force paths in init.py) and Phase 3 (lazy launch in lock/run for the force+launched test)
- **Polish (Phase 5)**: Depends on Phases 2–4 complete

### User Story Dependencies

```
Phase 1 (T001, T002) ──► Phase 2 (T003–T006) ──┐
                     └──► Phase 3 (T007–T012,T020) ──┼──► Phase 4 (T013–T014) ──► Phase 5 (T015–T019)
```

- **US1+US4 (Phase 2) and US2 (Phase 3)** can run in parallel after Phase 1 completes (different source files: `commands/init.py` vs `wrappers/workshop.py` + `commands/lock.py`)
- **US3 (Phase 4)** requires both Phase 2 and Phase 3 to be complete

### Within Each Phase

- Models before services, services before tests (where applicable)
- T003 → T004 → T005 (same file, sequential within Phase 2)
- T007 → T008 → T009 are sequential within Phase 3 (T009 uses T008's function)
- T006, T010, T011, T012 are [P] (different test files, no internal dependencies)

### Parallel Opportunities

- T001 and T002 (Phase 1) are [P]
- T006 (test_preconditions.py) is [P] with T003–T005 (different file)
- T007 and T008 (wrappers vs commands) are [P]
- T010, T011, T012, T020 (different test files) are all [P] within Phase 3
- T013 and T014 (different test functions in same file — technically sequential, but safe to batch as one task)
- T015, T016, T017 (different files) are all [P]; T018 and T019 are sequential (T019 after T018)

---

## Parallel Example: Phase 3 (US2)

```bash
# These can execute concurrently (different files):
Task T007: "Add ensure_launched() to src/microjail/wrappers/workshop.py"
Task T008: "Add ensure_container_ready() to src/microjail/commands/lock.py"
Task T010: "Add lazy-launch unit tests to tests/unit/commands/test_lock_command.py"
Task T011: "Update integration fixtures in tests/integration/commands/conftest.py"
Task T012: "Update init integration tests in tests/integration/commands/test_init_command.py"

# After T007 + T008 complete:
Task T009: "Update perform_lock() in src/microjail/commands/lock.py (uses both T007+T008)"
```

---

## Implementation Strategy

### MVP First (US1 — Thin init only)

1. Complete Phase 1: Foundational (T001–T002)
2. Complete Phase 2: US1+US4 source changes (T003–T005)
3. **STOP and VALIDATE**: `microjail init` exits 0 and makes zero subprocess calls; T006 passes
4. `microjail lock` fails with "not launched" error (expected at this stage — US2 not yet done)

### Incremental Delivery

1. Phase 1 → Foundation ready
2. Phase 2 → Thin init works (no container provisioning at init time)
3. Phase 3 → Lazy launch works (lock/run provision on first use)
4. Phase 4 → `--force` paths validated end-to-end
5. Phase 5 → Clean, ruff-compliant, documented

### Parallel Team Strategy

With two developers after Phase 1:
- **Developer A**: Phase 2 (US1 — thin init, `commands/init.py`)
- **Developer B**: Phase 3 (US2 — lazy launch, `wrappers/workshop.py` + `commands/lock.py`)
- Both: merge → Phase 4 (US3 integration tests) → Phase 5 (polish)

---

## Notes

- [P] tasks = different files, no blocking dependencies within the same phase
- [USN] label maps each task to a user story for traceability
- Constitution §II: `verify_exists` is still called after every `launch` — never skipped
- Constitution §I: `launched=True` must be persisted before `lock_egress` in T009 (FR-008)
- Do not use `# noqa` on any new code (constitution §IV)
- Commit after each checkpoint; checkpoints are marked in the task list
