---

description: "Task list for microjail init command"
---

# Tasks: microjail init Command

**Input**: Design documents from `specs/20260529-154152-init-command/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/cli.md ✅

**Tests**: Included for safety-critical paths (prerequisite checks, state round-trip, config
generators). Required by constitution Principle I — test-first for gate logic.

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story (US1, US2)
- File paths are relative to repository root

---

## Phase 1: Setup

**Purpose**: Add dependencies and create directory skeleton.

- [X] T001 Add `ruamel.yaml` to project dependencies in `pyproject.toml` (`uv add ruamel.yaml`)
- [X] T002 [P] Create source directory structure: `src/microjail/commands/`, `src/microjail/config/`, `src/microjail/workshop/` with `__init__.py` stubs in each
- [X] T003 [P] Create test directory structure: `tests/unit/`, `tests/integration/` with `__init__.py` stubs and `tests/conftest.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data types, subprocess wrapper, and state I/O that all user story phases depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 [P] Implement `EnvironmentConfig` and `InferenceBackend`/`AgentHarness` types in `src/microjail/config/models.py` per data-model.md; full type annotations; frozen dataclass
- [X] T005 [P] Implement `EnvironmentState` dataclass with `to_json()` / `from_json()` methods in `src/microjail/state.py`; write to `.microjail/state.json` using `pathlib`; ISO-8601 `created_at`
- [X] T006 [P] Implement Workshop/LXD subprocess wrapper in `src/microjail/workshop/client.py`: `check_prerequisites()`, `create(yaml_path)`, `verify_exists(name)` using `lxc info <name>`; all functions raise `RuntimeError` with actionable messages on failure
- [X] T006b [P] Implement workspace writability probe in `src/microjail/commands/init.py` (or a shared `preconditions.py` helper): before any file write, assert the current working directory exists and is writable using `os.access(cwd, os.W_OK)`; if not, exit non-zero with a message naming the path and the failure, without touching the Workshop CLI
- [X] T006c [P] Unit test for workspace writability probe in `tests/unit/test_preconditions.py`: mock `os.access` returning `False`; assert `RuntimeError` (or non-zero CLI exit) with a message containing the failing path; assert no `workshop` subprocess is called
- [X] T007 [P] Unit test for `state.py` in `tests/unit/test_state.py`: write then read round-trip; verify all fields survive serialisation; test `null` inference/agent case
- [X] T008 [P] Unit test for `workshop/client.py` prerequisite check in `tests/unit/test_workshop_client.py`: mock `shutil.which` and `subprocess.run`; assert correct `RuntimeError` messages when `workshop` absent and when `lxc` absent

**Checkpoint**: Foundational phase complete — user story phases may begin.

---

## Phase 3: User Story 1 — Jailed Environment for AI Agent (Priority: P1) 🎯 MVP

**Goal**: `microjail init myproject --inference llama-cpp --agent opencode` creates a Workshop
environment, writes `workshop.yaml` (opencode + skills SDKs, no tunnel), `opencode.jsonc`
(all remote providers disabled, llama.cpp provider active), and `.microjail/state.json`.

**Independent Test**: Run `microjail init myproject --inference llama-cpp --agent opencode` in
a clean directory; verify all four invariants from `contracts/cli.md` hold.

### Tests for User Story 1 ⚠️ Write and confirm failing before implementing T012

- [X] T009 [P] [US1] Unit test for `workshop.yaml` generator in `tests/unit/test_config_workshop.py`: assert `opencode` and `skills` SDKs present; assert no `system` SDK; assert no `tunnel`/`plugs`/`slots` keys; test bare (no-SDK) output; use `ruamel.yaml` to parse output and verify structure
- [X] T010 [P] [US1] Unit test for `opencode.jsonc` generator in `tests/unit/test_config_opencode.py`: assert all 10 known remote providers have `enabled: false`; assert `llama.cpp` provider present with no `npm` field; assert `context-mode` and `cc-safety-net` in `plugin` list; assert `$schema` present

### Implementation for User Story 1

- [X] T011 [P] [US1] Implement `workshop.yaml` generator in `src/microjail/config/workshop.py`: pure function `generate_workshop_yaml(config: EnvironmentConfig) -> str`; use `ruamel.yaml` for serialisation; no tunnel entries; opencode + skills SDKs when `agent == "opencode"`; empty SDK list for bare init
- [X] T012 [P] [US1] Implement `opencode.jsonc` generator in `src/microjail/config/opencode.py`: pure function `generate_opencode_config(socket_url: str) -> str`; all 10 remote providers set to `enabled: false`; no `npm` field; `context-mode` and `cc-safety-net` plugins; use `json.dumps` with `indent=4`
- [X] T013 [US1] Implement `init` command in `src/microjail/commands/init.py`: full orchestration per contracts/cli.md and FR-011 write-order (workshop.yaml → opencode.jsonc → state.json → `workshop create` → `lxc info` verify); state.json MUST be written before `workshop create` so a creation failure leaves no partial state inside the remote environment; handle `--force` flag; emit structured output to stdout via `rich`; all errors to stderr with correct exit codes per contract
- [X] T014 [US1] Register `init` command in `src/microjail/cli.py`: import and attach `app` from `src/microjail/commands/init.py`; verify `microjail init --help` output matches contract
- [X] T015 [US1] Integration test for full US1 path in `tests/integration/test_init_command.py` (`@pytest.mark.lxd`): invoke CLI via `typer.testing.CliRunner`; assert exit code 0; assert all files written; assert `lxc info myproject` exits 0; teardown: `workshop delete myproject`

**Checkpoint**: `microjail init myproject --inference llama-cpp --agent opencode` is fully
functional and independently testable.

---

## Phase 4: User Story 2 — Bare Environment (Priority: P2)

**Goal**: `microjail init myproject` (no flags) creates a Workshop environment with a minimal
`workshop.yaml` (empty SDK list) and no `opencode.jsonc`.

**Independent Test**: Run `microjail init bareproject`; assert `workshop.yaml` has empty `sdks`;
assert `opencode.jsonc` is absent; assert `lxc info bareproject` exits 0.

### Implementation for User Story 2

- [X] T016 [US2] Extend `init` command in `src/microjail/commands/init.py` to handle no-flags path: skip `opencode.jsonc` generation when `agent` is `None`; generate bare `workshop.yaml` (empty sdks) when both `inference` and `agent` are `None`; verify state.json `inference`/`agent` fields are `null`
- [X] T017 [US2] Integration test for bare init in `tests/integration/test_init_command.py` (`@pytest.mark.lxd`): assert `opencode.jsonc` absent; assert `workshop.yaml` has empty `sdks`; teardown: `workshop delete bareproject`

**Checkpoint**: Both user stories independently functional.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T018 [P] Run `ruff check --fix` and `ruff format` on all new source files; run `ty check src/` and resolve any type errors
- [X] T019 [P] Update `README.md`: replace illustrative usage block with the actual `microjail init` flags and options as implemented; add prerequisite install note referencing Workshop

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately; T002 and T003 are parallel
- **Foundational (Phase 2)**: Depends on Phase 1 completion; T004–T008 (including T006b, T006c) all parallel
- **User Story 1 (Phase 3)**: Depends on Phase 2 completion; T009–T012 parallel, T013 depends on T011+T012+T006, T014 depends on T013, T015 depends on T014
- **User Story 2 (Phase 4)**: Depends on Phase 3 completion (reuses infrastructure)
- **Polish (Phase 5)**: Depends on all story phases complete

### Within Phase 3

```
T009 [P] ─┐
T010 [P] ─┤  (write failing tests first)
T011 [P] ─┤
T012 [P] ─┘
            └─→ T013 (init command — depends on T011, T012, T006)
                    └─→ T014 (CLI wiring)
                              └─→ T015 (integration test — requires LXD)
```

### Parallel Opportunities

```bash
# Phase 2 — all parallel:
Task: "T004 Implement EnvironmentConfig in src/microjail/config/models.py"
Task: "T005 Implement EnvironmentState in src/microjail/state.py"
Task: "T006 Implement workshop client in src/microjail/workshop/client.py"
Task: "T006b Implement workspace writability probe in src/microjail/commands/init.py"
Task: "T006c Unit test for workspace writability probe in tests/unit/test_preconditions.py"
Task: "T007 Unit test for state.py in tests/unit/test_state.py"
Task: "T008 Unit test for workshop client in tests/unit/test_workshop_client.py"

# Phase 3 — parallel until T013:
Task: "T009 Unit test workshop.yaml generator in tests/unit/test_config_workshop.py"
Task: "T010 Unit test opencode.jsonc generator in tests/unit/test_config_opencode.py"
Task: "T011 Implement workshop.yaml generator in src/microjail/config/workshop.py"
Task: "T012 Implement opencode.jsonc generator in src/microjail/config/opencode.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: `microjail init myproject --inference llama-cpp --agent opencode` passes all invariants from `contracts/cli.md`
5. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → skeleton and data types ready
2. User Story 1 → full agent init path → test independently → **MVP**
3. User Story 2 → bare init path → test independently
4. Polish → clean types, updated README

---

## Notes

- `[P]` tasks operate on different files with no incomplete-task dependencies
- T015 and T017 require `@pytest.mark.lxd` and a live Workshop + LXD installation; skip with `pytest -m "not lxd"` for local unit-only runs
- `pylxd` is NOT used in this feature; if no other feature needs it, remove from `pyproject.toml` as part of T001
- The `baseURL` value in `opencode.jsonc` (UDS path vs HTTP loopback) is an implementation-time decision; see `research.md §3`; T012 accepts it as a parameter
- Avoid: vague task descriptions, same-file conflicts between parallel tasks, cross-story dependencies that break independent testability
