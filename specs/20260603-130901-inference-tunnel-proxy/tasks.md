# Tasks: Inference Tunnel Proxy

**Input**: Design documents from `specs/20260603-130901-inference-tunnel-proxy/`

**Prerequisites**: plan.md, spec.md, data-model.md, research.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Minimal — modifies existing codebase)

**Purpose**: Ensure existing tests pass before modifications begin

- [ ] T001 Verify existing test suite passes: `pytest tests/unit/ tests/integration/ -v`
- [ ] T002 Review `src/microjail/config/workshop.py` current YAML generation logic
- [ ] T003 Review `src/microjail/gates/inference_socket.py` current UDS + TCP gate logic
- [ ] T004 Review `src/microjail/lxd/network.py` current lock_egress/unlock_egress implementation

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core network and YAML generation changes that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T005 [P] Modify `src/microjail/lxd/network.py` `_nic_device()` to `_all_nic_devices()` — enumerate ALL LXD devices whose type contains "nic" (returns list instead of single device)
- [ ] T006 Modify `src/microjail/lxd/network.py` `lock_egress()` to iterate over ALL NIC devices and clear `ipv4.routes.external` and `ipv6.routes.external` on each
- [ ] T007 Modify `src/microjail/lxd/network.py` `unlock_egress()` to iterate over ALL NIC devices and restore routes on each (symmetric to lock)
- [ ] T008 Modify `src/microjail/lxd/network.py` `unlock_egress()` to re-add the container to `workshopbr0` network if the container is running (check via `lxc info <container>` status)
- [ ] T009 Modify `src/microjail/config/workshop.py` `generate_workshop_yaml()` to accept `inference: str | None` parameter
- [ ] T010 [P] Add tunnel slot/plug generation in `src/microjail/config/workshop.py` — when `inference` is not None, generate: (a) `system` SDK entry with `slots.{inference}` using `interface: tunnel` and `endpoint: localhost:8080`, (b) project SDK entry named `{inference}` with `plugs.{inference}` using `interface: tunnel`
- [ ] T011 Ensure `src/microjail/config/workshop.py` places system SDK and project inference SDK AFTER `opencode` and `skills` entries (FR-012)

**Checkpoint**: Foundation ready — network enumeration works, tunnel YAML generates correctly

---

## Phase 3: User Story 1 — Workshop YAML Tunnel Generation (Priority: P1) 🎯 MVP

**Goal**: `microjail init --inference llama-cpp --agent opencode` generates a `workshop.yaml` with system SDK tunnel slot and project SDK tunnel plug

**Independent Test**: Run `microjail init myproject --inference llama-cpp --agent opencode`; verify generated `.workshop/myproject.yaml` contains `system` SDK with `slots.llama-cpp.interface: tunnel` and `llama-cpp` project SDK with `plugs.llama-cpp.interface: tunnel`; verify no system SDK when `--inference` omitted

- [ ] T012 [US1] Wire `src/microjail/commands/init.py` to pass `config.inference` to `generate_workshop_yaml()` call
- [ ] T013 [US1] Verify `workshop.yaml` output: when `--inference llama-cpp` is set, system SDK slot has `endpoint: localhost:8080` (derived from `_SOCKET_URL` host:port)
- [ ] T014 [US1] Verify `workshop.yaml` output: when `--inference llama-cpp` is NOT set, no system SDK and no tunnel entries appear
- [ ] T015 [US1] Add integration test in `tests/integration/test_init_command.py` asserting tunnel YAML structure for `--inference llama-cpp`
- [ ] T016 [US1] Add integration test in `tests/integration/test_init_command.py` asserting NO tunnel entries when `--inference` omitted
- [ ] T017 [US1] Add integration test in `tests/integration/test_init_command.py` asserting `--force` re-initialisation refreshes Workshop environment with tunnel config (FR-013 / SC-004)

**Checkpoint**: User Story 1 fully functional — init generates correct tunnel YAML

---

## Phase 4: User Story 2 — Inference Gate TCP-Only Check (Priority: P1)

**Goal**: The inference gate pivots from UDS socket file check to TCP reachability check

**Independent Test**: Initialise with `--inference llama-cpp`; run `microjail run -- echo hello` without llama-server → exits non-zero with "not reachable" message; start llama-server on port 8080 → gate passes

- [ ] T018 [US2] Rename `src/microjail/gates/inference_socket.py` to `src/microjail/gates/inference_tunnel.py`
- [ ] T019 [US2] Update `src/microjail/gates/__init__.py` import: change `from microjail.gates.inference_socket import check_inference_socket` to `from microjail.gates.inference_tunnel import check_inference_tunnel`
- [ ] T020 [US2] Update `src/microjail/gates/__init__.py` call site: change `check_inference_socket(state.socket_url)` to `check_inference_tunnel(state.socket_url)`
- [ ] T021 [US2] In `src/microjail/gates/inference_tunnel.py`, remove `_UDS_SCHEMES` constant, `_extract_socket_path()` function, and `_check_uds()` function entirely
- [ ] T022 [US2] In `src/microjail/gates/inference_tunnel.py`, rename `check_inference_socket()` to `check_inference_tunnel()` and make it directly call `_check_tcp()` (no dispatch logic needed)
- [ ] T023 [US2] Update `GateResult` name from `"inference-socket"` to `"inference-tunnel"` in the renamed gate function
- [ ] T024 [US2] Verify gate still returns `GateResult(True, ...)` when `state.inference` is None (skipped)
- [ ] T025 [US2] Verify gate reports host and port in failure message (FR-009)
- [ ] T026 [US2] Update `tests/unit/test_gates_inference_socket.py` — rename file to `test_gates_inference_tunnel.py` and rewrite tests for TCP-only behavior
- [ ] T027 [US2] Add unit test: gate passes when TCP port is reachable
- [ ] T028 [US2] Add unit test: gate fails with host:port message when TCP port is not reachable
- [ ] T029 [US2] Add unit test: gate is skipped when `state.inference` is None

**Checkpoint**: User Story 2 fully functional — gate checks TCP, no UDS code remains

---

## Phase 5: User Story 3 — State File Tunnel Endpoint (Priority: P1)

**Goal**: `socket_url` in state.json is an HTTP URL (already true — verify no regression)

**Independent Test**: Run `microjail init myproject --inference llama-cpp`; read `.microjail/state.json`; verify `socket_url` is `http://127.0.0.1:8080/v1`; verify `socket_url` is `null` without `--inference`

- [ ] T030 [US3] Verify `src/microjail/commands/init.py` writes `socket_url` as HTTP URL (`http://127.0.0.1:8080/v1`) when `--inference llama-cpp` is set
- [ ] T031 [US3] Verify `src/microjail/commands/init.py` writes `socket_url` as `null` when `--inference` is NOT set
- [ ] T032 [US3] Verify `src/microjail/config/opencode.py` uses `socket_url` for `baseURL` without modification (already works, confirm no regression)
- [ ] T033 [US3] Add integration test in `tests/integration/test_init_command.py` asserting `state.json` contains HTTP URL for `socket_url`

**Checkpoint**: User Story 3 verified — state records correct endpoint type

---

## Phase 6: User Story 4 — UDS Configuration Cleanup (Priority: P2)

**Goal**: No UDS bind-mount or socket file references remain in inference-related code paths

**Independent Test**: Search codebase for `uds`, `unix`, `socket_path`, `bind-mount` in `src/microjail/config/`, `src/microjail/gates/`, `src/microjail/commands/` — verify zero matches related to inference

- [ ] T034 [US4] Search and verify: no UDS socket path generation in `src/microjail/config/` (no `http+unix://` or `unix://` URLs generated)
- [ ] T035 [US4] Search and verify: no UDS file existence checks in `src/microjail/gates/` (already done in US2, double-check)
- [ ] T036 [US4] Search and verify: no bind-mount references for inference in `src/microjail/commands/` or config
- [ ] T037 [US4] Remove any dead code in `src/microjail/gates/inference_tunnel.py` that was left behind from UDS removal
- [ ] T038 [US4] Run full test suite to confirm no regressions from UDS removal

**Checkpoint**: All user stories independently functional

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and cleanup

- [ ] T039 [P] Update `tests/unit/test_gates_egress.py` if needed for multi-NIC lock/unlock behavior
- [ ] T040 [P] Add unit tests for `src/microjail/lxd/network.py` `lock_egress()` / `unlock_egress()` with multiple NICs
- [ ] T041 [P] Add unit test for `unlock_egress()` workshopbr0 re-attachment when container running
- [ ] T042 Add unit test for `unlock_egress()` skipping workshopbr0 re-attachment when container not running
- [ ] T043 Run full test suite: `pytest tests/unit/ tests/integration/ -v`
- [ ] T044 Verify quickstart.md steps work end-to-end (manual validation)
- [ ] T045 Run ruff/mypy checks: `ruff check src/microjail/ && mypy src/microjail/`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories. T005-T011 must complete first.
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - US1 (P1) and US2 (P1) can proceed in parallel after Foundation
  - US3 (P1) depends on US1 completion (needs init to generate state correctly)
  - US4 (P2) cleanup can proceed in parallel once US2 is done
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational — No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational — No dependencies on other stories
- **User Story 3 (P1)**: Depends on US1 (needs correct state generation) — can start once US1 done
- **User Story 4 (P2)**: Depends on US2 (needs UDS fully removed) — can start once US2 done

### Within Each User Story

- Core implementation before tests
- Tests should fail before implementation is verified (if adding new tests)
- Story complete before moving to next priority

### Parallel Opportunities

- T005-T011 in Foundational: T005, T009, T010 can be worked in parallel (different files)
- T012-T017 in US1: T012-T014 can be parallel; T015-T017 (tests) after implementation
- T018-T029 in US2: T018-T024 (core rename/refactor) sequential; T026-T029 (tests) after
- T030-T033 in US3: T030-T032 can be parallel; T033 (test) after
- T034-T038 in US4: T034-T037 can be parallel; T038 (validation) after

---

## Parallel Example: User Story 1 + User Story 2 (after Foundation)

```bash
# Developer A: Workshop YAML generation (US1)
Task: "Wire init.py to pass inference to generate_workshop_yaml()"
Task: "Verify workshop.yaml tunnel structure for --inference llama-cpp"

# Developer B: Gate pivot (US2) — different files, no dependency on US1
Task: "Rename inference_socket.py to inference_tunnel.py"
Task: "Remove all UDS code paths from inference gate"
Task: "Update gates/__init__.py import and call site"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1 (YAML generation)
4. Complete Phase 4: User Story 2 (gate pivot)
5. **STOP and VALIDATE**: Test US1 + US2 independently
6. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently
3. Add User Story 2 → Test independently
4. Add User Story 3 → Test independently (state verification)
5. Add User Story 4 → Test independently (cleanup)
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (workshop.py YAML)
   - Developer B: User Story 2 (gate rename + TCP pivot)
3. Once US1 + US2 complete:
   - Developer A: User Story 3 (state verification)
   - Developer B: User Story 4 (UDS cleanup)
4. Polish phase together

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- No new external dependencies needed (ruamel.yaml, typer, pytest already present)
- The rename `inference_socket.py` → `inference_tunnel.py` is a breaking change for any external importers; none exist in this codebase
- Lock/unlock changes affect ALL microjail environments, not just inference ones — verify backward compatibility
