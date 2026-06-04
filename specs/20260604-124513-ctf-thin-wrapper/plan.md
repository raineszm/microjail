# Implementation Plan: CTF Thin Wrapper

**Branch**: `20260604-124513-ctf-thin-wrapper` | **Date**: 2026-06-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/20260604-124513-ctf-thin-wrapper/spec.md`

## Summary

Migrate `microjail/config/workshop.py` from inline plug/slot YAML declarations to the project-SDK pattern proven by `ctf/workshop_config.py`, adding `generate_sdk_yaml()` alongside the existing `generate_workshop_yaml()`. Extend `EnvironmentConfig` with `inference_endpoint: str | None` and `AgentHarness` with `"omp"`, give `microjail init` a `--inference-url` flag and a post-launch `workshop connect` step, and narrow the `check_config_readonly` gate to `opencode` only. `ctf/main.py` drops its private `workshop_config.py` and manual state dict, delegating to the same config/state machinery used by the normal `microjail` workflow. The final state is one YAML-generation code path shared by both the standard tool and the escape test, with `ctf/workshop_config.py` deleted.

## Technical Context

**Language/Version**: Python 3.14 — same `pyproject.toml` and `.venv` as the main project.

**Primary Dependencies** (all already present):
- `ruamel-yaml` — YAML generation (unchanged)
- `typer` — CLI (adding one flag to `init`)
- `stdlib: urllib.parse` — URL parsing for `--inference-url`

**Storage**: `.microjail/state.json` (existing, unchanged format). New: `.workshop/local-inference/sdk.yaml` written by `microjail init` and by `ctf/main.py`.

**Testing**: pytest (existing). Unit tests cover every changed module. No new integration test markers required — all changes are pure config generation or gate logic.

**Target Platform**: Linux (Ubuntu) — unchanged.

**Project Type**: Refactor of an existing CLI tool + deletion of a parallel implementation.

**Performance Goals**: No change — pure I/O (YAML generation, file writes, one subprocess call added to `init`).

**Constraints**:
- The `ctf/` tree MUST NOT be imported by any `microjail.*` module (unchanged).
- No new third-party dependencies.
- `generate_workshop_yaml` signature is unchanged; existing callers need no update for the YAML output format (the format changes, but callers only write the result to disk).
- `EnvironmentConfig(name, base_image, inference, agent)` positional construction continues to work (new field has default).

**Scale/Scope**: 6 source files changed, 2 test files deleted, 1 test file updated, 7 new test functions added.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Safety First | ✅ PASS | Lock/unlock lifecycle is unchanged. `check_config_readonly` gate narrowing is a correction (the gate was spuriously failing for non-opencode agents, not a safety regression). Adding `workshop connect` to `init` is additive; no connect call means the tunnel isn't wired, not that egress is compromised. CTF still calls `lock_egress` before the monitoring loop. |
| II. Correctness Over Confidence | ✅ PASS | `generate_sdk_yaml` uses `rpartition(":")` for unambiguous port extraction and raises `ValueError` on malformed input (not silently wrong). The connect call in `init` propagates `RuntimeError` via `_err()` — no silent swallow. `EnvironmentState.to_json()` is the established, tested path for state persistence. |
| III. Human Readability & Auditability | ✅ PASS | Deleting `ctf/workshop_config.py` removes a parallel implementation that auditors had to cross-check. `INFERENCE_PLUG_REF` / `INFERENCE_SLOT_REF` constants make the wiring explicit. `generate_sdk_yaml` is clearly named and single-purpose. |
| IV. Idiomatic Python | ✅ PASS | `inference_endpoint: str | None = None` is the standard frozen-dataclass pattern for optional fields. No `# noqa` suppressions. `urlparse` reused from stdlib (CTF already uses it). All new public functions have type annotations and docstrings. |
| V. Fail Loudly, Fail Clearly | ✅ PASS | `--inference-url` validation mirrors CTF's existing check (scheme + hostname). sdk.yaml write wrapped in `try/except OSError` → `_err(..., code=3)`. Connect failure → `_err(..., code=3)`. `generate_sdk_yaml` raises `ValueError` on bad endpoint — surfaces as an unhandled exception with a clear message at the call site. |

No violations. No Complexity Tracking entry required.

## Project Structure

### Documentation (this feature)

```text
specs/20260604-124513-ctf-thin-wrapper/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── checklists/
    └── requirements.md
```

### Source Code Changes

```text
CHANGED
  src/microjail/config/models.py      # AgentHarness += "omp"; EnvironmentConfig += inference_endpoint
  src/microjail/config/workshop.py    # generate_workshop_yaml updated; generate_sdk_yaml + constants added
  src/microjail/commands/init.py      # --inference-url flag; sdk.yaml write; connect step
  src/microjail/gates/__init__.py     # check_config_readonly gated on agent == "opencode"
  ctf/main.py                         # use microjail config/state; import constants; drop hardcoded strings
  tests/unit/test_config_workshop.py  # 6 tests updated + 7 new tests

DELETED
  ctf/workshop_config.py
  tests/unit/test_ctf_workshop_config.py
```

**Structure Decision**: Flat `src/microjail/config/` module unchanged. No new packages. `ctf/` package loses one module and references two new imports from microjail.

---

## Phase 0: Research

**Output**: [research.md](research.md) — all unknowns resolved from codebase reading.

### R-001 — `workshop connect` approach

**Status**: RESOLVED ✅

**Decision**: Add module-level constants `INFERENCE_PLUG_REF = "local-inference:llama"` and `INFERENCE_SLOT_REF = "system:llama"` to `microjail/config/workshop.py`. `microjail init` calls `workshop_client.connect(name, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF, workspace)` post-launch. `ctf/main.py` replaces its inline hardcoded strings with the same imported constants — the connect invocation is NOT dropped from CTF (CTF manages its own temp workspace outside `init`'s flow), but the string literals are no longer duplicated.

No `connect_inference()` wrapper: a wrapper in `client.py` would couple the client module to the config naming. Constants in `config/workshop.py` keep the coupling at the config layer.

### R-002 — `generate_sdk_yaml` port extraction

**Status**: RESOLVED ✅

**Decision**: `rpartition(":")` on `inference_endpoint`; raise `ValueError` if no colon. If `inference_endpoint` is `None`, apply default `"localhost:8080"` before extraction. The plug endpoint in sdk.yaml is always `localhost:{port}` (container-side).

### R-003 — `--inference-url` parsing

**Status**: RESOLVED ✅

**Decision**: Replicate CTF's `urlparse` pattern (already in `ctf/main.py` lines 155–165). Derive `inference_endpoint = f"{parsed.hostname}:{inf_port}"`. Port defaults to 443/80 by scheme if absent. Scheme + hostname validation at argument parse time (`_err(..., code=1)`).

### R-004 — `sdk.yaml` write timing

**Status**: RESOLVED ✅

**Decision**: Write in `_write_config_files` (before `_launch_and_verify`). Workshop reads project SDK directories during `workshop launch` — sdk.yaml must exist before the launch call.

### R-005 — `EnvironmentConfig` field ordering

**Status**: RESOLVED ✅

**Decision**: Append `inference_endpoint: str | None = None` as the last field. Frozen dataclass rule satisfied (field with default follows all fields without defaults).

### R-006 — Tests breaking after migration

**Status**: RESOLVED ✅

**Decision**: Six existing test assertions change (see data-model.md for the full table). Seven new tests added to cover `generate_sdk_yaml`, `omp` agent, and configurable endpoint.

---

## Phase 1: Design & Contracts

**Prerequisites**: research.md complete ✅

### Data model → [data-model.md](data-model.md)

See `data-model.md` for complete entity and function contracts.

Key changes at a glance:

| Entity | Change |
|--------|--------|
| `AgentHarness` | `Literal["opencode", "omp"]` |
| `EnvironmentConfig` | +`inference_endpoint: str \| None = None` |
| `generate_workshop_yaml` | project-SDK output; `llama` slot key; configurable endpoint |
| `generate_sdk_yaml` (new) | sdk.yaml generator; plug `llama` at `localhost:{port}` |
| `INFERENCE_PLUG_REF` (new) | `"local-inference:llama"` |
| `INFERENCE_SLOT_REF` (new) | `"system:llama"` |
| `microjail init` | `--inference-url`; sdk.yaml write; connect post-launch |
| `run_all_gates` | `check_config_readonly` gated on `agent == "opencode"` |
| `ctf/main.py` | use microjail generators + `EnvironmentState.to_json()` + shared constants |

### Workshop YAML contract → [data-model.md](data-model.md)

YAML examples for all config combinations are in `data-model.md`.

### Developer guide → [quickstart.md](quickstart.md)

Step-by-step implementation guide with code snippets.

### Agent context update

The `AGENTS.md` plan reference already points to the CTF escape-test plan (`specs/20260604-084221-ctf-escape-test/plan.md`). Update to point to this plan:

```
specs/20260604-124513-ctf-thin-wrapper/plan.md
```
