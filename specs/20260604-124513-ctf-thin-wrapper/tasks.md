# Tasks: CTF Thin Wrapper

**Input**: Design documents from `specs/20260604-124513-ctf-thin-wrapper/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [data-model.md](data-model.md), [quickstart.md](quickstart.md), [research.md](research.md)

**Tests**: Included — existing test suite must stay green; test files listed in data-model.md are updated/deleted as part of implementation.

**Organization**: Tasks ordered by dependency. US2/US3/US4 (microjail feature flags) are built before US1 (CTF thin wrapper) because US1 depends on them.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared in-flight dependencies)
- **[Story]**: User story label (US1–US4)

---

## Phase 1: Foundational — Data Model Changes

**Purpose**: Type and config changes that all user stories depend on. Must complete before any user story phase.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T001 Extend `AgentHarness` literal to include `"omp"`; update `SUPPORTED_AGENTS = ("opencode", "omp")`; update `_validate_inputs` in `src/microjail/commands/init.py` to check `agent not in SUPPORTED_AGENTS` (remove hardcoded `"opencode"` string); append `inference_endpoint: str | None = None` field to `EnvironmentConfig` — in `src/microjail/config/models.py` and `src/microjail/commands/init.py`

**Checkpoint**: `EnvironmentConfig(name, base, inference, agent)` still constructs; `EnvironmentConfig(name, base, inference, agent, inference_endpoint="host:port")` also works. `AgentHarness` validation accepts `"omp"`. `microjail init myenv --agent omp` reaches preflight without error.

---

## Phase 2: User Story 4 — Gate Scope Fix (Priority: P3)

**Goal**: Narrow `check_config_readonly` to `agent == "opencode"` only so omp and future non-opencode agents don't cause spurious gate failures.

**Independent Test**: Build `EnvironmentState(agent="omp", ...)` and call `run_all_gates`; assert no `config_readonly` result is returned. Build with `agent="opencode"`; assert it is returned.

- [x] T002 [US4] Change gate condition from `state.agent is not None` to `state.agent == "opencode"` in `src/microjail/gates/__init__.py`
- [x] T003 [P] [US4] Update `tests/unit/test_gates_config_readonly.py`: add test that `config_readonly` is absent for `agent="omp"` and `agent=None`; verify existing opencode test still asserts presence

**Checkpoint**: `pytest tests/unit/test_gates_config_readonly.py -v` green. Gate returns no `config_readonly` for omp state.

---

## Phase 3: User Story 2 — omp Agent Type (Priority: P2)

**Goal**: `generate_workshop_yaml` emits `{name: omp, channel: 14/edge}` with no `skills` SDK when `agent="omp"`.

**Independent Test**: `generate_workshop_yaml(EnvironmentConfig(name="x", base_image="ubuntu@24.04", inference=None, agent="omp"))` contains `name: omp` + `channel: 14/edge` + no `skills` entry.

- [x] T004 [US2] Add `elif config.agent == "omp": sdks = [{"name": "omp", "channel": "14/edge"}]` branch in `generate_workshop_yaml` in `src/microjail/config/workshop.py`
- [x] T005 [P] [US2] Update `tests/unit/test_config_workshop.py`: add `test_omp_agent_sdk_present` (asserts `name: omp`, `channel: 14/edge`) and `test_omp_no_skills_sdk` (asserts no `skills` entry when `agent="omp"`)

**Checkpoint**: `pytest tests/unit/test_config_workshop.py -v` green including new omp tests.

---

## Phase 4: User Story 3 — Project-SDK Migration & Configurable Endpoint (Priority: P2)

**Goal**: `generate_workshop_yaml` uses project-SDK pattern; `generate_sdk_yaml` produces `.workshop/local-inference/sdk.yaml`; `microjail init` writes both files and calls `workshop connect`.

**Independent Test**: `generate_workshop_yaml(EnvironmentConfig(..., inference="llama-cpp", inference_endpoint="192.168.1.5:9000"))` contains `project-local-inference` SDK reference and system slot `llama` at `192.168.1.5:9000`. `generate_sdk_yaml` with same config produces plug `llama` at `localhost:9000`.

### Implementation for User Story 3

- [x] T006 [US3] Add module-level constants `INFERENCE_PLUG_REF = "local-inference:llama"` and `INFERENCE_SLOT_REF = "system:llama"` at top of `src/microjail/config/workshop.py`
- [x] T007 [US3] Migrate inference block in `generate_workshop_yaml`: replace inline plug SDK entry with `{"name": "project-local-inference"}`; change system slot key from `llama-cpp` to `llama`; use `config.inference_endpoint or "localhost:8080"` as endpoint — in `src/microjail/config/workshop.py`
- [x] T008 [US3] Add `generate_sdk_yaml(config: EnvironmentConfig) -> str` function: returns empty string when `inference is None`; extracts port via `rpartition(":")` on `inference_endpoint or "localhost:8080"`; emits `name: local-inference`, `plugs.llama.interface: tunnel`, `plugs.llama.endpoint: localhost:{port}` — in `src/microjail/config/workshop.py`
- [x] T009 [US3] Add `--inference-url` flag to `init()`: parse with `urlparse`, validate scheme + hostname, derive `inference_endpoint = f"{host}:{port}"` (port defaults to 80/443 by scheme), derive `socket_url = f"http://localhost:{port}/v1"` — in `src/microjail/commands/init.py`
- [x] T010 [US3] Extend `_write_config_files` to write `.workshop/local-inference/sdk.yaml` when `config.inference is not None`: call `generate_sdk_yaml(config)`, write to `workspace / ".workshop" / "local-inference" / "sdk.yaml"` — in `src/microjail/commands/init.py`
- [x] T011 [US3] Add post-launch connect step to `init()` after `_launch_and_verify`: call `client.connect(name, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF, workspace)` when `inference is not None`; wrap in `try/except RuntimeError` → `_err(..., code=3)` — in `src/microjail/commands/init.py`
- [x] T012 [P] [US3] Update `tests/unit/test_config_workshop.py`: fix 6 breaking tests (slot key `llama-cpp`→`llama`, `llama-cpp` SDK name→`project-local-inference`, SDK ordering now `opencode/skills/project-local-inference/system`, no inline `plugs` in workshop.yaml); add 7 new tests: `test_generate_sdk_yaml_with_custom_endpoint`, `test_generate_sdk_yaml_default_endpoint`, `test_generate_sdk_yaml_returns_empty_no_inference`, `test_configurable_endpoint_in_system_slot`, `test_opencode_inference_uses_project_sdk`, `test_generate_sdk_yaml_raises_on_malformed_endpoint`, `test_inference_sdk_name_is_project_local_inference`; update `_full_config()` with `inference_endpoint="localhost:8080"`

**Checkpoint**: `pytest tests/unit/test_config_workshop.py -v` green (all 6 updated + all 7 new). `microjail init myenv --inference llama-cpp` writes both workshop.yaml and `.workshop/local-inference/sdk.yaml`.

---

## Phase 5: User Story 1 — CTF Thin Wrapper (Priority: P1)

**Goal**: `ctf/main.py` uses microjail's config/state machinery exclusively; `ctf/workshop_config.py` deleted.

**Independent Test**: Run `ctf` with a valid inference URL; verify state.json matches `EnvironmentState` structure (not the old `_STATE_JSON_TEMPLATE` dict); verify workshop YAML was generated via `generate_workshop_yaml`; verify `ctf.workshop_config` module no longer exists.

### Implementation for User Story 1

- [x] T013 [US1] Replace imports in `ctf/main.py`: remove `from ctf.workshop_config import generate_ctf_workshop_yaml, generate_inference_sdk_yaml`; add `from microjail.config.models import EnvironmentConfig`; add `from microjail.config.workshop import generate_workshop_yaml, generate_sdk_yaml, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF`; add `from microjail.state import EnvironmentState`; remove now-unused `import json` and `_STATE_JSON_TEMPLATE` constant — in `ctf/main.py`
- [x] T014 [US1] Replace CTF workshop YAML generation block in `ctf/main.py`: construct `EnvironmentConfig(name=env_name, base_image="ubuntu@24.04", inference="llama-cpp", agent="omp", inference_endpoint=f"{inference_host}:{inference_port}")`; write workshop YAML via `generate_workshop_yaml(config)`; write sdk.yaml via `generate_sdk_yaml(config)` into `workshop_dir / "local-inference" / "sdk.yaml"` — in `ctf/main.py`
- [x] T015 [US1] Replace manual state dict construction in `ctf/main.py`: construct `EnvironmentState(name=env_name, base_image="ubuntu@24.04", inference="llama-cpp", agent="omp", socket_url=f"http://localhost:{inference_port}/v1", created_at=datetime.now(UTC))`; call `state.to_json(workspace)`; remove `_STATE_JSON_TEMPLATE` and the `state_doc` dict + `json.dumps` block — in `ctf/main.py`
- [x] T016 [US1] Replace hardcoded connect string literals with shared constants in `ctf/main.py`: change `workshop_client.connect(env_name, "local-inference:llama", "system:llama", workspace)` to `workshop_client.connect(env_name, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF, workspace)` — in `ctf/main.py`
- [x] T017 [P] [US1] Delete `ctf/workshop_config.py`
- [x] T018 [P] [US1] Delete `tests/unit/test_ctf_workshop_config.py`

**Checkpoint**: `ctf/workshop_config.py` gone. `from ctf.workshop_config import ...` raises `ModuleNotFoundError`. `pytest tests/unit/test_ctf_main.py -v` green.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Test suite verification, cleanup of test_ctf_main.py if it references deleted modules, final validation.

- [x] T019 [P] Audit `tests/unit/test_ctf_main.py` for any remaining imports from `ctf.workshop_config` and remove them; update any assertions that tested the old manual state dict format or the old workshop YAML structure; **add `patch("ctf.main.workshop_client.connect")` to the `patched_env` fixture** — without this mock every `patched_env` test that asserts `exit_code == 0` will fail because the real `connect()` raises in CI
- [x] T020 Run full unit suite `pytest tests/unit/ -v` and confirm all tests green; fix any remaining breakage
- [x] T021 [P] Update `microjail init` success output to print `.workshop/local-inference/sdk.yaml` path when inference is configured — in `src/microjail/commands/init.py`

**Checkpoint**: `pytest tests/unit/ -v` — all green, no skips related to changed code. `ctf/workshop_config.py` absent. AGENTS.md plan reference already updated.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — start immediately.
- **US4 (Phase 2)**: Depends only on Phase 1 (uses `EnvironmentState.agent`).
- **US2 (Phase 3)**: Depends only on Phase 1 (uses `EnvironmentConfig.agent`).
- **US3 (Phase 4)**: Depends on Phase 1 (uses `EnvironmentConfig.inference_endpoint`). T007 depends on T006; T008 depends on T006; T009–T011 in `init.py` depend on T006–T008 being present (need `INFERENCE_PLUG_REF`/`generate_sdk_yaml`).
- **US1 (Phase 5)**: Depends on US2 (needs omp in YAML) + US3 (needs `generate_workshop_yaml`/`generate_sdk_yaml`/constants). Phase 2/US4 recommended but not strictly blocking for CTF.
- **Polish (Phase 6)**: Depends on US1 complete.

### User Story Dependencies

```
Phase 1 (Foundational)
  ├── Phase 2 (US4): independent, can run after Phase 1
  ├── Phase 3 (US2): independent, can run after Phase 1
  └── Phase 4 (US3): can run after Phase 1; T010-T011 need T006-T008 done
       └── Phase 5 (US1): needs Phase 3 + Phase 4 complete
            └── Phase 6 (Polish)
```

US2 and US4 can run in parallel after Phase 1. US3 can also run after Phase 1 and in parallel with US2/US4 (all in different files after T006 is done).

### Within-Phase Parallelism

- **Phase 4 US3**: T006–T008 (workshop.py) sequential; T009–T011 (init.py) sequential; T012 (tests) parallel with T009–T011.
- **Phase 5 US1**: T013–T016 (ctf/main.py) sequential; T017+T018 (deletions) parallel with each other and after T013.

---

## Parallel Example: User Story 3

```bash
# After T006 (constants) and T007 (generate_workshop_yaml) are done:
Task A: "T008 — add generate_sdk_yaml to src/microjail/config/workshop.py"
Task B: "T009 — add --inference-url flag to src/microjail/commands/init.py"
# Task B does not touch workshop.py — can proceed in parallel with Task A.
# T010, T011 depend on T009 (same file); T012 (tests) can proceed in parallel with T010/T011.
```

---

## Implementation Strategy

### MVP First (US3 + US1: the core refactor)

1. Complete Phase 1: Foundational data model changes.
2. Complete Phase 4 US3: project-SDK migration (core generator changes + init).
3. Complete Phase 5 US1: CTF thin wrapper (deletes ctf/workshop_config.py).
4. **STOP and VALIDATE**: `pytest tests/unit/ -v` green; `ctf/workshop_config.py` absent.
5. Then add US2 (omp) and US4 (gate fix) as incremental completions.

### Full Incremental Delivery

1. Phase 1 → data model ready.
2. Phase 2 (US4) + Phase 3 (US2) in parallel → gate and omp support ready.
3. Phase 4 (US3) → project-SDK pattern live in microjail.
4. Phase 5 (US1) → CTF is now a thin wrapper.
5. Phase 6 (Polish) → full suite green, cleanup done.

---

## Notes

- 21 total tasks; 7 parallelizable (`[P]` marked).
- No new test files created — all test changes are updates/deletions to existing files.
- `[P]` on T012 means it can be written concurrently while T009–T011 are being implemented, since T012 touches only `tests/unit/test_config_workshop.py`.
- T017 and T018 are file deletions — no implementation required, just `rm`.
- The `inference_endpoint` format is `"host:port"` (no scheme, no path). Port is always explicit after parsing `--inference-url`.
