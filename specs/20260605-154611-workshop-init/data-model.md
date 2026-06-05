# Data Model: Thin-Wrapper Init with Lazy Container Launch

**Feature**: `specs/20260605-154611-workshop-init/spec.md`
**Date**: 2026-06-05

---

## Entity: `State`

**File**: `src/microjail/state.py`
**Persisted at**: `<workspace>/.microjail/state.json`

### Fields

| Field | Type | Default | Persisted | Description |
|---|---|---|---|---|
| `name` | `str` | required | yes | Workshop environment name. Matches `^[a-zA-Z][a-zA-Z0-9-]*$`, max 63 chars. |
| `base_image` | `str` | required | yes | LXD base image string, e.g. `ubuntu@26.04`. Fixed to `ubuntu@26.04` in current implementation. |
| `inference` | `str \| None` | required | yes | Inference backend (`"llama-cpp"`), or `None`. |
| `agent` | `str \| None` | required | yes | Agent harness (`"opencode"` or `"omp"`), or `None`. |
| `socket_url` | `str \| None` | required | yes | Inference endpoint URL (`http://localhost:PORT/v1`), or `None`. |
| `locked` | `bool` | `False` | yes | Whether egress is currently severed and the state file is read-only inside the container. |
| **`launched`** *(new)* | `bool` | **`True`** | yes | Whether the Workshop container has been successfully provisioned and verified at least once in this workspace. Default `True` for backward compatibility with existing state files written before this field was introduced. New `microjail init` writes `False` explicitly. |

### Backward Compatibility

Old `state.json` files (written before this change) lack the `launched` key. `msgspec` uses the field default (`True`) for absent keys, consistent with the `locked` field pattern. A `True` default correctly represents "was already launched when this file was written" for all pre-existing environments.

### Valid State Combinations

| `launched` | `locked` | Name | Entry condition |
|---|---|---|---|
| `False` | `False` | *configured* | After `microjail init` (new behavior) |
| `True` | `False` | *ready* | After `microjail lock` / `run` complete; after `init --force` on launched env |
| `True` | `True` | *locked* | During `microjail lock` or `microjail run` execution |
| `False` | `True` | **invalid** | Must never occur; code prevents this by design |

### State Transitions

```
                 microjail init
                      │
                      ▼
            ┌─────────────────┐
            │  configured     │  launched=False, locked=False
            │  (new default)  │
            └────────┬────────┘
                     │ microjail lock / run
                     │ (lazy launch: ensure_launched → persist launched=True → lock_egress)
                     ▼
            ┌─────────────────┐
            │     locked      │  launched=True, locked=True
            └────────┬────────┘
                     │ microjail unlock / run completes
                     ▼
            ┌─────────────────┐
            │     ready       │  launched=True, locked=False
            └────────┬────────┘
                     │ microjail init --force (launched=True, locked=False)
                     │ (refresh + verify + reconnect tunnel)
                     ▼
            ┌─────────────────┐
            │     ready       │  launched=True, locked=False (updated config)
            └─────────────────┘

            microjail init --force on configured (launched=False):
            ┌─────────────────┐    ┌─────────────────┐
            │  configured     │───▶│  configured     │  (files overwritten, no Workshop call)
            └─────────────────┘    └─────────────────┘
```

### Invariants

- `locked=True` implies `launched=True`. Code enforces this: `lock_egress` is never reached unless `ensure_container_ready` has succeeded (or was skipped because `launched` was already `True`).
- `launched` transitions `False → True` inside `ensure_container_ready`, never inside the wrapper layer.
- `launched` is never set back to `False` by any current operation (even `init --force` on an already-launched env keeps `launched=True` after refresh).
- `launched` is only written once `workshop.verify_exists()` has confirmed the postcondition (constitution §II).

---

## Entity: `EnvironmentConfig`

**File**: `src/microjail/config/models.py`
**Persisted**: never — in-memory only

No change. Carries user intent from CLI arguments to config file generators. The `launched` lifecycle concept does not exist in this entity; it is purely a `State` concern.

---

## Filesystem artefacts written by `microjail init`

| Path | Written by | Written when | Notes |
|---|---|---|---|
| `.workshop/<name>.yaml` | `write_config_files()` | Every `init` (and `--force`) | Workshop reads this at launch time. Written before `state.json`. |
| `.workshop/local-inference/sdk.yaml` | `write_config_files()` | When `--inference` is set | |
| `opencode.jsonc` | `write_config_files()` | When `--agent opencode` | |
| `.microjail/state.json` | `state.dump()` | Every `init` (after config files) | Now includes `launched=false`. Written last. |

**No new filesystem artefacts** are introduced by this feature. The container lifecycle state (`launched`) is tracked inside the existing `state.json`.
