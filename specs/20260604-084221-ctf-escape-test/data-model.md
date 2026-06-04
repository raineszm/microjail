# Data Model: CTF Thin Wrapper

**Branch**: `20260604-084221-ctf-escape-test` | **Plan**: [plan.md](plan.md)

This document supersedes and extends the original data-model for the CTF escape-test feature,
covering the thin-wrapper changes that wire the `omp` agent harness and the local-inference
tunnel into the core `microjail` init/run path alongside the existing `opencode` path.

---

## Changed Entities

### `AgentHarness` (`src/microjail/config/models.py`)

```python
# Before
AgentHarness = Literal["opencode"]
SUPPORTED_AGENTS: tuple[str, ...] = ("opencode",)

# After
AgentHarness = Literal["opencode", "omp"]
SUPPORTED_AGENTS: tuple[str, ...] = ("opencode", "omp")
```

`"omp"` is the Workshop-packaged agent harness used by the CTF runner. It does **not** require
a companion `skills` SDK — only the `omp` snap itself.

---

### `EnvironmentConfig` (`src/microjail/config/models.py`)

New field added to the frozen dataclass:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `inference_endpoint` | `str \| None` | `None` | Inference server address in `host:port` form, e.g. `"192.168.1.5:8080"`. No scheme, no path. |

```python
@dataclass(frozen=True)
class EnvironmentConfig:
    name: str
    base_image: str
    inference: InferenceBackend | None
    agent: AgentHarness | None
    inference_endpoint: str | None = None   # NEW
```

**Invariants**:
- When set, the format is `host:port` with no URL scheme and no trailing path. Callers are
  responsible for validation before constructing the config.
- `None` means "use `localhost:8080`" in every generated YAML file.
- This field is **never persisted** to `state.json` (`EnvironmentState` does not change). It
  is an ephemeral hint passed through the file-generation layer only.

---

## New Constants

### `INFERENCE_PLUG_REF`, `INFERENCE_SLOT_REF` (`src/microjail/config/workshop.py`)

```python
INFERENCE_PLUG_REF: str = "local-inference:llama"
INFERENCE_SLOT_REF: str = "system:llama"
```

These constants identify the two sides of the Workshop tunnel that bridges the host inference
server into the container. They are consumed by:

- `microjail init` — calls `workshop_client.connect(name, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF, workspace)` after launching the environment.
- `ctf/main.py` — the same `connect` call, replacing the previously inline string literals
  `"local-inference:llama"` and `"system:llama"`.

Keeping them in `workshop.py` avoids duplication and ensures the plug and slot names stay in
sync with the YAML generators that produce them.

---

## Changed Function Contracts

### `generate_workshop_yaml(config: EnvironmentConfig) -> str`

Location: `src/microjail/config/workshop.py`

The function signature is **unchanged**. The output changes as follows:

#### Inference SDK block

| | Before | After |
|---|---|---|
| Project SDK entry | `{name: llama-cpp, plugs: {llama-cpp: {interface: tunnel}}}` | `{name: project-local-inference}` (bare reference, no inline plugs) |
| System slot key | `llama-cpp` | `llama` |
| System slot endpoint | hardcoded `"localhost:8080"` | `config.inference_endpoint or "localhost:8080"` |

The plug declaration moves into the project SDK's own `sdk.yaml` (see `generate_sdk_yaml`
below). The workshop environment YAML references the project SDK by name only; Workshop
discovers the plug definition when it loads the SDK directory.

#### Agent SDK block

| `config.agent` | SDKs emitted |
|----------------|--------------|
| `"opencode"` | `opencode` (latest/stable) + `skills` (latest/edge) — **unchanged** |
| `"omp"` | `omp` (14/edge) only — **no** `skills` SDK |
| `None` | no agent SDKs emitted — **unchanged** |

#### Full output examples

**`agent="opencode"`, `inference="llama-cpp"`, `inference_endpoint="192.168.1.5:8080"`**:

```yaml
name: myproject
base: ubuntu@26.04
sdks:
  - name: opencode
    channel: latest/stable
  - name: skills
    channel: latest/edge
  - name: project-local-inference
  - name: system
    slots:
      llama:
        interface: tunnel
        endpoint: 192.168.1.5:8080
```

**`agent="omp"`, `inference="llama-cpp"`, `inference_endpoint="10.0.0.1:9090"`**:

```yaml
name: ctf-ab12cd34
base: ubuntu@26.04
sdks:
  - name: omp
    channel: 14/edge
  - name: project-local-inference
  - name: system
    slots:
      llama:
        interface: tunnel
        endpoint: 10.0.0.1:9090
```

**`agent=None`, `inference=None`** (bare init):

```yaml
name: bareproject
base: ubuntu@26.04
sdks: []
```

---

### `generate_sdk_yaml(config: EnvironmentConfig) -> str` (NEW)

Location: `src/microjail/config/workshop.py`

Generates the content of `.workshop/local-inference/sdk.yaml`. This file declares the plug
that the project SDK contributes to the Workshop connection model.

**Signature**:

```python
def generate_sdk_yaml(config: EnvironmentConfig) -> str: ...
```

**Behaviour**:

| Condition | Return value |
|-----------|-------------|
| `config.inference is None` | `""` (empty string — caller must not write the file) |
| `config.inference is not None` | YAML string declaring a `llama` tunnel plug at `localhost:{port}` |

**Port extraction**: `config.inference_endpoint.rpartition(':')[2]` when
`config.inference_endpoint` is not `None`; falls back to `"8080"` when
`inference_endpoint` is `None`.

The plug `endpoint` always uses `localhost` as the host because it is the container-side
address that Workshop binds after the tunnel is connected — it does **not** use the
host-side address from `inference_endpoint` (that goes in the `system` slot in the
workshop YAML).

**Output example** (port 8080):

```yaml
name: local-inference
plugs:
  llama:
    interface: tunnel
    endpoint: localhost:8080
```

**Output example** (port 9090, `inference_endpoint="10.0.0.1:9090"`):

```yaml
name: local-inference
plugs:
  llama:
    interface: tunnel
    endpoint: localhost:9090
```

---

## Changed Command Contracts

### `microjail init` (`src/microjail/commands/init.py`)

#### New CLI flag

```
--inference-url URL   (optional)
```

`URL` is a full URL with scheme, e.g. `http://192.168.1.5:8080`. The port is extracted
with `urlparse(URL).port or 8080`; the resulting `host:port` string populates
`config.inference_endpoint`.

#### `_validate_inputs` change

`agent` validation must now accept `"omp"` in addition to `"opencode"`:

```python
if agent is not None and agent not in {"opencode", "omp"}:
    _err(...)
```

#### `socket_url` derivation change

| Condition | `socket_url` value |
|-----------|-------------------|
| `inference is None` | `None` (unchanged) |
| `inference is not None` and `--inference-url` not provided | `"http://127.0.0.1:8080/v1"` (unchanged) |
| `inference is not None` and `--inference-url` provided | `"http://localhost:{port}/v1"` where `port` comes from `urlparse(inference_url).port or 8080` |

#### `_write_config_files` new step

After writing `.workshop/<name>.yaml`, when `config.inference is not None`:

1. Create `.workshop/local-inference/` directory.
2. Write `generate_sdk_yaml(config)` to `.workshop/local-inference/sdk.yaml`.

```python
sdk_dir = workspace / ".workshop" / "local-inference"
sdk_dir.mkdir(exist_ok=True)
(sdk_dir / "sdk.yaml").write_text(generate_sdk_yaml(config))
```

#### New step after `_launch_and_verify`

When `config.inference is not None`, connect the tunnel:

```python
workshop_client.connect(
    name, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF, workspace
)
```

This mirrors the existing call in `ctf/main.py` and uses the same constants.

#### File layout after `microjail init myenv --inference llama-cpp --agent omp --inference-url http://10.0.0.1:9090`

```
<cwd>/
  .workshop/
    myenv.yaml                    # environment definition
    local-inference/
      sdk.yaml                    # plug declaration
  .microjail/
    state.json                    # persisted state (inference_endpoint NOT stored)
```

---

### `run_all_gates` (`src/microjail/gates/__init__.py`)

The `config-readonly` gate now guards only when `state.agent == "opencode"`, not whenever
`state.agent is not None`:

```python
# Before
if state.agent is not None:
    results.append(check_config_readonly(workspace))

# After
if state.agent == "opencode":
    results.append(check_config_readonly(workspace))
```

**Rationale**: `check_config_readonly` checks for `opencode.jsonc`. The `omp` harness does
not use that file; running the gate against an `omp` environment would always fail (the file
does not exist) or produce a spurious pass. The gate is semantically tied to opencode.

The docstring for `run_all_gates` must be updated to reflect this:

```
# Before
- ``config-readonly``: ``opencode.jsonc`` is not writable (only when agent is set).

# After
- ``config-readonly``: ``opencode.jsonc`` is not writable (only when agent == "opencode").
```

---

## Files Written to Workspace

The table from the original data-model extends with the sdk.yaml path:

| Host path | Container path | Written by | Purpose |
|-----------|----------------|------------|---------|
| `<ws>/.workshop/<env>.yaml` | n/a | runner / init | Workshop environment definition |
| `<ws>/.workshop/local-inference/sdk.yaml` | n/a | runner / init | Plug declaration for inference tunnel |
| `<ws>/.microjail/state.json` | n/a | init / runner | Required by `lock_egress` |
| `<ws>/agent_script.sh` | `/project/agent_script.sh` | runner (copy) | In-container agent loop |
| `<ws>/ctf_prompt.txt` | `/project/ctf_prompt.txt` | runner | Prompt for `omp` |
| `<ws>/confirmed` | `/project/confirmed` | agent (touch) | Agent acknowledges task |
| `<ws>/escape-notes.md` | `/project/escape-notes.md` | agent | Persistent scratch notes |
| `<ws>/secret-found.txt` | `/project/secret-found.txt` | agent | Signal file: secret retrieved |

---

## Workshop YAML Structure (revised)

The system SDK slot key changes from `llama-cpp` to `llama`; the project SDK entry is now a
bare reference (the plug lives in `sdk.yaml`):

```yaml
name: ctf-<env_name>
base: ubuntu@24.04
sdks:
  - name: omp
    channel: 14/edge
  - name: project-local-inference
  - name: system
    slots:
      llama:
        interface: tunnel
        endpoint: "<inference_host>:<inference_port>"
```

And the companion `sdk.yaml` for the project SDK:

```yaml
name: local-inference
plugs:
  llama:
    interface: tunnel
    endpoint: "localhost:<inference_port>"
```

Workshop auto-connects `project-local-inference:llama` → `system:llama` when the environment
is launched. The explicit `workshop_client.connect(...)` call in the runner triggers this
connection after launch (required when auto-connect is not triggered by Workshop automatically).

---

## Broken Tests Requiring Updates

### `tests/unit/test_config_workshop.py`

All tests that hard-code the `llama-cpp` SDK/slot/plug names fail after the rename.

| Test | What breaks | Required fix |
|------|-------------|--------------|
| `test_inference_sdk_endpoint` | Looks up `system_sdk["slots"]["llama-cpp"]`; key is now `"llama"` | Change lookup key to `"llama"` |
| `test_inference_sdk_plugs` | Looks up `sdk["name"] == "llama-cpp"` and `sdk["plugs"]["llama-cpp"]`; both gone | The project SDK is now a bare reference — either assert `{name: project-local-inference}` with no `plugs`, or remove the inline-plugs assertion and add a separate test for `generate_sdk_yaml` |
| `test_inference_sdk_slots` | Looks up `system_sdk["slots"]["llama-cpp"]`; key is now `"llama"` | Change lookup key to `"llama"` |
| `test_sdk_ordering` | Asserts `["opencode", "skills", "llama-cpp", "system"]`; third entry is now `"project-local-inference"` | Update expected list |
| `test_inference_sdk_absent_when_no_inference` | Asserts `"llama-cpp" not in sdk_names`; correct name is now `"project-local-inference"` | Update the asserted name |
| `test_tunnel_keys_present_when_inference_set` | Asserts `"plugs"` appears in the YAML string; the project SDK no longer has inline plugs | Remove `"plugs"` from the checked keys, or rewrite to assert `"project-local-inference"` is present |

New tests needed in this file:
- `test_omp_agent_emits_omp_sdk` — `agent="omp"` produces `{name: omp, channel: 14/edge}`.
- `test_omp_agent_no_skills_sdk` — `agent="omp"` does NOT produce a `skills` entry.
- `test_inference_endpoint_used_in_system_slot` — when `config.inference_endpoint` is set,
  its value appears in `system.slots.llama.endpoint`.
- Tests for `generate_sdk_yaml`:
  - returns empty string when `config.inference is None`.
  - returns valid YAML with `plugs.llama.endpoint = localhost:8080` when port is `8080`.
  - port is extracted correctly from `inference_endpoint = "192.168.1.5:9090"` → `localhost:9090`.

### `tests/unit/test_ctf_main.py`

The `patched_env` fixture does not patch `workshop_client.connect`. After this change, `connect` is called in Phase 1 of `ctf/main.py`. Without the patch the fixture will attempt a real Workshop call and fail (or raise `AttributeError` in a mock that does not have `connect`).

**Fix**: add `patch("ctf.main.workshop_client.connect")` to the `with (...)` block in `patched_env`.

### `tests/unit/test_ctf_workshop_config.py`

No breakage — this file tests `ctf.workshop_config` which already uses `llama`/`project-local-inference` and is not changed by this feature. Tests remain valid as a regression guard.

### `tests/unit/test_gates_config_readonly.py`

The gate function itself (`check_config_readonly`) does not change. Tests remain valid.

Tests for `run_all_gates` dispatching (currently only exercised indirectly through
`test_lock_command.py` via mock) should be updated or added to assert that
`check_config_readonly` is **not** called when `state.agent == "omp"`.

### `tests/integration/test_init_command.py`

Any integration test that calls `microjail init --agent opencode` against a live Workshop
installation is unaffected. Tests that validate the generated YAML content and check for
`llama-cpp` slot/plug names will fail and must be updated to expect `llama`/`project-local-inference`.

---

## Entities unchanged

- `Secret`, `TestRunConfig`, `TestRun`, `ContainmentReport` — no changes.
- `EnvironmentState` (`src/microjail/state.py`) — `inference_endpoint` is not persisted; the
  persisted schema is unchanged.
- `generate_ctf_workshop_yaml` (`ctf/workshop_config.py`) — already uses the correct
  `project-local-inference` / `llama` names; no change required.
- `generate_inference_sdk_yaml` (`ctf/workshop_config.py`) — already generates the correct
  plug YAML; `generate_sdk_yaml` in `workshop.py` is a parallel implementation for the `init`
  command path. The two functions produce identical output for the same port.
