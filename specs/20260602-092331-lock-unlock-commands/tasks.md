---
description: "Task list for lock, unlock, and run commands"
---

# Tasks: microjail lock, unlock, and run Commands

**Input**: Design documents from `specs/20260602-092331-lock-unlock-commands/`

**Prerequisites**: plan.md ✅, spec.md ✅

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US4)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the `locked` field to `EnvironmentState` and wire the new commands into
the CLI. All subsequent phases depend on this.

- [X] T001 Add `locked: bool = False` field to `EnvironmentState` in `src/microjail/state.py` and update `to_json`/`from_json` to serialise/deserialise it
- [X] T002 Create `src/microjail/lxd/__init__.py` (empty package marker)
- [X] T003 Create `src/microjail/gates/__init__.py` with `GateResult` dataclass (`name: str`, `passed: bool`, `message: str`) and `run_all_gates()` function signature
- [X] T004 Register `lock`, `unlock`, and `run` commands in `src/microjail/cli.py` (stubs that raise `NotImplementedError` until implemented)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Egress control and gate infrastructure must exist before any command can be
implemented. All user story phases depend on this.

**⚠️ CRITICAL**: No command implementation can begin until this phase is complete.

- [X] T005 Implement `src/microjail/lxd/network.py` with `lock_egress(container: str) -> None` and `unlock_egress(container: str) -> None` using `lxc` subprocess calls to sever and restore container network egress; `lock_egress` MUST also add a named `readonly=true` disk device for `.microjail/state.json` via `lxc config device add`; `unlock_egress` MUST remove the device via `lxc config device remove`; raise `RuntimeError` with actionable message on failure
- [X] T006 [P] Implement `src/microjail/gates/egress.py` — gate that probes from inside the container to an external IP (e.g. `8.8.8.8`) via `lxc exec` and confirms the probe fails; returns `GateResult`
- [X] T007 [P] Implement `src/microjail/gates/workspace.py` — gate that verifies the workspace directory is bind-mounted inside the container at the expected path via `lxc config show`; returns `GateResult`
- [X] T008 [P] Implement `src/microjail/gates/config_readonly.py` — gate (skipped when `state.agent` is `None`) that checks `opencode.jsonc` in the workspace is not world-writable; returns `GateResult`
- [X] T008a [P] Implement `src/microjail/gates/state_readonly.py` — unconditional gate that verifies the `readonly=true` LXD disk device for `.microjail/state.json` is present and active by inspecting `lxc config device show <container>`; returns `GateResult`; does NOT use `lxc exec -- test -w` (which checks filesystem permissions, not the mount device)
- [X] T009 [P] Implement `src/microjail/gates/inference_socket.py` — gate (skipped when `state.inference` is `None`) that verifies the UDS socket path from `state.socket_url` exists and accepts a connection; returns `GateResult`
- [X] T010 Implement `run_all_gates(state: EnvironmentState, workspace: Path) -> list[GateResult]` in `src/microjail/gates/__init__.py`; always run egress, workspace, and state-readonly gates; conditionally run config-readonly (agent set) and inference-socket (inference set) gates; return all results
- [X] T011 Add `exec(container: str, cmd: list[str], project_dir: Path) -> subprocess.CompletedProcess` to `src/microjail/workshop/client.py` for running commands inside the container
- [X] T015 [P] Write unit tests in `tests/unit/test_gates_egress.py` mocking `lxc exec` to simulate egress up and egress down states — MUST demonstrate gate blocks when egress is up (constitution: test-first for gate logic)
- [X] T016 [P] Write unit tests in `tests/unit/test_gates_workspace.py` mocking `lxc config show` for mount present and mount absent — MUST include blocking case
- [X] T017 [P] Write unit tests in `tests/unit/test_gates_config_readonly.py` covering agent-present/absent and writable/readonly cases — MUST include blocking case
- [X] T017a [P] Write unit tests in `tests/unit/test_gates_state_readonly.py` covering state file writable and readonly cases (unconditional gate) — MUST include blocking case
- [X] T018 [P] Write unit tests in `tests/unit/test_gates_inference_socket.py` covering inference-present/absent and socket-reachable/missing cases — MUST include blocking case

**Checkpoint**: Egress control, all gates, and gate unit tests implemented — command phases can now proceed in parallel.

---

## Phase 3: User Story 1 — Lock and run a workload (Priority: P1) 🎯 MVP

**Goal**: `microjail run -- <cmd>` locks the environment, verifies all gates, spawns the
workload inside the container, then unlocks after exit.

**Independent test**: `microjail run -- echo hello` executes, exits with the workload's
exit code, and no external host is reachable from inside the container during execution.

- [X] T012 [US1] Implement `src/microjail/commands/lock.py` internal helper `perform_lock(state, workspace)` — calls `lxd.network.lock_egress()`, runs `gates.run_all_gates()`, rolls back egress via `lxd.network.unlock_egress()` on any gate failure, updates `state.locked = True` and persists state on success; raises `RuntimeError` naming the failing gate
- [X] T013 [US1] Implement `src/microjail/commands/run.py` — load state, reject empty workload before locking, call `perform_lock()`, spawn workload via `workshop.client.exec()`, call `lxd.network.unlock_egress()` + update state after workload exits, exit with workload's exit code
- [X] T014 [US1] Wire `microjail run` into `src/microjail/cli.py` replacing the stub
- [X] T019 [P] [US1] Write unit tests in `tests/unit/test_state_locked_field.py` for `locked` field round-trip and default value
- [X] T020 [US1] Write integration test `tests/integration/test_run_command.py` (`@pytest.mark.lxd`): run `microjail run -- echo hello`, assert exit code 0 and egress unreachable during run

---

## Phase 4: User Story 2 — Unlock to restore networking (Priority: P1)

**Goal**: `microjail unlock` restores egress and updates state; idempotent.

**Independent test**: After `microjail run` completes, `microjail unlock` exits zero and
a network probe from inside the container succeeds.

- [X] T021 [US2] Implement `src/microjail/commands/unlock.py` — load state, if already unlocked print informational message and exit zero, else call `lxd.network.unlock_egress()`, update `state.locked = False`, persist state
- [X] T022 [US2] Wire `microjail unlock` into `src/microjail/cli.py` replacing the stub
- [X] T023 [P] [US2] Write unit tests for `unlock` command: already-unlocked idempotency, successful unlock, missing state file error
- [X] T024 [US2] Write integration test `tests/integration/test_unlock_command.py` (`@pytest.mark.lxd`): lock environment, run `microjail unlock`, assert egress is restored

---

## Phase 5: User Story 3 — Standalone lock command (Priority: P1)

**Goal**: `microjail lock` as a standalone command — severs egress, runs all gates,
rolls back on failure, idempotent on already-locked environments.

**Independent test**: `microjail lock` exits zero, state records locked, and network probe
from inside the container fails; no workload is spawned.

- [X] T025 [US3] Implement the `microjail lock` typer command in `src/microjail/commands/lock.py` — load state, if already locked print informational message and exit zero, else call `perform_lock()` (reusing the helper from T012), exit zero on success or non-zero naming the failing gate
- [X] T026 [US3] Wire `microjail lock` into `src/microjail/cli.py` replacing the stub
- [X] T027 [P] [US3] Write unit tests for `lock` command: already-locked idempotency, gate failure triggers egress rollback, successful lock updates state, missing state file error
- [X] T028 [US3] Write integration test `tests/integration/test_lock_command.py` (`@pytest.mark.lxd`): run `microjail lock`, assert state locked and egress unreachable; run `microjail unlock` to clean up

---

## Phase 6: User Story 4 — Inference socket gate (Priority: P2)

**Goal**: When `--inference llama-cpp` was set at init, the inference socket gate fires
and blocks the run if the socket is absent.

**Independent test**: Init with `--inference llama-cpp`; run `microjail run` without a
socket file present; assert non-zero exit naming the missing socket path.

- [X] T029 [US4] Extend integration test `tests/integration/test_run_command.py` with an inference-socket-missing scenario: init with `--inference llama-cpp`, omit socket file, assert `microjail run` exits non-zero and names the socket path in the error
- [X] T030 [P] [US4] Extend integration test with inference-socket-present scenario: place a mock UDS socket at the expected path and assert the inference gate passes

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T031 [P] Add rich console output to `lock`, `unlock`, and `run` commands: gate-by-gate progress lines, final success/failure summary consistent with `init` command output style
- [ ] T032 [P] Add `--help` text and usage examples to `lock`, `unlock`, and `run` commands matching the style of `microjail init --help` in the README
- [X] T034 Implement run-log writer: after workload exits in `src/microjail/commands/run.py`, append a JSONL entry to `.microjail/run-log.jsonl` containing workload command tokens, UTC start time, gate results (name + passed), and exit code; raise on write failure (constitution §Security — audit trail)
- [X] T035 [P] Write unit tests in `tests/unit/test_run_log.py`: assert log entry is written on successful run, assert log entry is written even when workload exits non-zero, assert log is append-only across multiple runs
- [X] T033 Verify all new code passes `pre-commit` hooks (ruff, mypy) by running `pre-commit run --all-files`

---

## Dependencies

```
Phase 1 (Setup)
  └── Phase 2 (Foundations: lxd/network.py, gates/)
        ├── Phase 3 (US1: run)      ← can proceed after Phase 2
        ├── Phase 4 (US2: unlock)   ← can proceed after Phase 2; T021 independent of Phase 3
        └── Phase 5 (US3: lock)     ← depends on T012 (perform_lock helper) from Phase 3
              └── Phase 6 (US4: inference socket integration tests)
                    └── Phase 7 (Polish)
```

Within Phase 2, T006–T009 and T008a (individual gates) and T015–T018 and T017a (gate unit tests) are fully parallel to each other; tests MUST be co-merged with their gate implementation.
Within Phase 3, T015–T019 (unit tests) are parallel to each other and to T012–T013.
Within Phase 4, T023 is parallel to T021–T022.

## Parallel Execution Examples

**Phase 2 (after T005 merges)**:
- Agent A: T006 (egress gate) + T015 (egress test) + T008 (config-readonly gate) + T017 (config-readonly test) + T008a (state-readonly gate) + T017a (state-readonly test)
- Agent B: T007 (workspace gate) + T016 (workspace test) + T009 (inference-socket gate) + T018 (inference-socket test)
- Agent C: T011 (workshop exec wrapper)
→ Converge on T010 (run_all_gates)

**Phase 3 + Phase 4 (after Phase 2 merges)**:
- Agent A: T012→T013→T014→T020 (run command end-to-end)
- Agent B: T021→T022→T023→T024 (unlock command end-to-end)
→ Converge on Phase 5 (lock command, which reuses T012's helper)

## Implementation Strategy

**MVP scope**: Phase 1 + Phase 2 + Phase 3 + Phase 4 = `run` and `unlock` fully working
with all five baseline gates and their unit tests. This delivers the complete core lifecycle (init → provision →
run → unlock).

Phase 5 (standalone `lock`) and Phase 6 (inference integration tests) are independently
additive and can follow in a second pass.
