# Data Model: CTF Thin Wrapper

**Phase 1 output for** `specs/20260604-124513-ctf-thin-wrapper/plan.md`

---

## Changed Types

### `AgentHarness` (`src/microjail/config/models.py`)

```python
# Before
AgentHarness = Literal["opencode"]

# After
AgentHarness = Literal["opencode", "omp"]
```

`"omp"` uses channel `14/edge` in the generated workshop YAML. It does **not** emit a `skills` SDK entry.

---

### `EnvironmentConfig` (`src/microjail/config/models.py`)

New field appended last (after `agent`) so existing positional callers are unaffected:

```python
@dataclass(frozen=True)
class EnvironmentConfig:
    name: str
    base_image: str
    inference: InferenceBackend | None
    agent: AgentHarness | None
    inference_endpoint: str | None = None   # NEW
    """Host-side inference endpoint as 'host:port' (no scheme, no path).

    None means default to localhost:8080 in generated YAML.
    Populated from --inference-url by stripping scheme and path:
      http://192.168.1.5:9000/v1  ->  "192.168.1.5:9000"
    Used by generate_workshop_yaml (system slot endpoint) and
    generate_sdk_yaml (plug endpoint port extraction).
    Never persisted; EnvironmentState.socket_url is derived from this.
    """
```

---

## Changed Functions

### `generate_workshop_yaml(config: EnvironmentConfig) -> str`

**Location**: `src/microjail/config/workshop.py`
**Signature**: unchanged.

**Changed behaviour when `config.inference is not None`:**

| Before (inline plug/slot) | After (project-SDK) |
|--------------------------|---------------------|
| Emitted `{name: llama-cpp, plugs: {llama-cpp: {interface: tunnel}}}` | Emitted `{name: project-local-inference}` (bare reference, no `plugs` key) |
| System slot key: `llama-cpp` | System slot key: `llama` |
| System slot endpoint: hardcoded `localhost:8080` | System slot endpoint: `config.inference_endpoint or "localhost:8080"` |

**Changed behaviour when `config.agent == "omp"`:**

- Emits `{name: omp, channel: "14/edge"}` — one SDK entry.
- Does **not** emit `skills` SDK (that is opencode-only).

**Unchanged behaviour:**

- `agent == "opencode"` still emits opencode (`latest/stable`) + skills (`latest/edge`).
- `inference is None` still emits no tunnel SDKs.
- `name`, `base` fields unchanged.

#### Output examples

**opencode + llama-cpp, no `--inference-url`:**
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
        endpoint: localhost:8080
```

**omp + llama-cpp, `--inference-url http://192.168.1.5:9000`:**
```yaml
name: ctf-abc123
base: ubuntu@24.04
sdks:
  - name: omp
    channel: 14/edge
  - name: project-local-inference
  - name: system
    slots:
      llama:
        interface: tunnel
        endpoint: 192.168.1.5:9000
```

**No inference (any agent):**
```yaml
name: myproject
base: ubuntu@26.04
sdks:
  - name: opencode
    channel: latest/stable
  - name: skills
    channel: latest/edge
```

---

## New Functions

### `generate_sdk_yaml(config: EnvironmentConfig) -> str`

**Location**: `src/microjail/config/workshop.py`
**Purpose**: Produces the `.workshop/local-inference/sdk.yaml` content for the project-SDK inference tunnel.

```python
def generate_sdk_yaml(config: EnvironmentConfig) -> str:
    """Return sdk.yaml for the local-inference project SDK.

    Returns an empty string when config.inference is None (caller must gate).
    Raises ValueError if config.inference_endpoint contains no port separator.
    """
```

**Port extraction:**
```
endpoint = config.inference_endpoint or "localhost:8080"
_, sep, port_str = endpoint.rpartition(":")
if not sep:
    raise ValueError(f"inference_endpoint {endpoint!r} contains no port")
port = int(port_str)
```

**Output** (for `inference_endpoint="192.168.1.5:9000"`):
```yaml
name: local-inference
plugs:
  llama:
    interface: tunnel
    endpoint: localhost:9000
```

**Output** (for `inference_endpoint=None`):
```yaml
name: local-inference
plugs:
  llama:
    interface: tunnel
    endpoint: localhost:8080
```

---

### `INFERENCE_PLUG_REF`, `INFERENCE_SLOT_REF` (new constants)

**Location**: `src/microjail/config/workshop.py`

```python
INFERENCE_PLUG_REF: str = "local-inference:llama"
INFERENCE_SLOT_REF: str = "system:llama"
```

Consumed by `microjail init` (`_connect_inference_if_needed`) and `ctf/main.py` (replaces inline string literals). Centralises the plug/slot naming so renaming requires one edit.

---

## Changed Logic

### `run_all_gates` (`src/microjail/gates/__init__.py`)

```python
# Before
if state.agent is not None:
    results.append(check_config_readonly(workspace))

# After
if state.agent == "opencode":
    results.append(check_config_readonly(workspace))
```

`check_config_readonly` verifies `opencode.jsonc` exists and is read-only — a file only created by `microjail init --agent opencode`. Running it for `agent="omp"` (or any future non-opencode agent) would always fail spuriously.

---

## Changed Command: `microjail init`

**New flag:**
```
--inference-url URL    HTTP/HTTPS URL of the inference server (e.g. http://192.168.1.5:8080).
                       Scheme and path are stripped; stored as host:port in EnvironmentConfig.
                       Optional; omitting uses localhost:8080 for all inference endpoints.
```

**New steps in `_write_config_files`** (after writing workshop.yaml):
```python
if config.inference is not None:
    sdk_yaml_content = generate_sdk_yaml(config)
    sdk_dir = workspace / ".workshop" / "local-inference"
    sdk_dir.mkdir(parents=True, exist_ok=True)
    (sdk_dir / "sdk.yaml").write_text(sdk_yaml_content)
```

**New step after `_launch_and_verify`:**
```python
if config.inference is not None:
    try:
        client.connect(name, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF, workspace)
    except RuntimeError as exc:
        _err(str(exc), code=3)
```

**`socket_url` derivation change** (for `--inference-url`):
```python
# Before: always http://127.0.0.1:8080/v1
# After: when inference_url is provided, derive port from it
socket_url = f"http://localhost:{inference_port}/v1" if inference else None
```

**Updated `--force` behaviour**: `.workshop/local-inference/sdk.yaml` is overwritten silently when `--force` is passed, consistent with `--force` overwriting `.workshop/{name}.yaml`.

---

## Changed Module: `ctf/main.py`

| Removed | Replaced with |
|---------|---------------|
| `from ctf.workshop_config import generate_ctf_workshop_yaml, generate_inference_sdk_yaml` | `from microjail.config.workshop import generate_workshop_yaml, generate_sdk_yaml, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF` |
| `from microjail.config.models import EnvironmentConfig` (new import) | — |
| Manual `_STATE_JSON_TEMPLATE` dict + `json.dumps` | `EnvironmentState(...).to_json(workspace)` |
| `(sdk_dir / "sdk.yaml").write_text(generate_inference_sdk_yaml(inference_port))` | `generate_sdk_yaml(config)` call in config block |
| `workshop_client.connect(env_name, "local-inference:llama", "system:llama", workspace)` | `workshop_client.connect(env_name, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF, workspace)` |
| Inline workshop YAML generation via `generate_ctf_workshop_yaml` | `generate_workshop_yaml(EnvironmentConfig(...))` |

**socket_url** in CTF's `EnvironmentState`: `f"http://localhost:{inference_port}/v1"` (container-side URL; `inference_port` already extracted from `--inference-url`).

---

## Deleted

- `ctf/workshop_config.py` — entirely replaced by `microjail.config.workshop`
- `tests/unit/test_ctf_workshop_config.py` — coverage moves to `test_config_workshop.py`

---

## Tests Requiring Update (`tests/unit/test_config_workshop.py`)

| Test | Change |
|------|--------|
| `test_tunnel_keys_present_when_inference_set` | Assert `project-local-inference` in SDK names; remove assertion about inline `plugs` key |
| `test_inference_sdk_endpoint` | Slot key changes to `llama`; assert `slots["llama"]["endpoint"]` |
| `test_inference_sdk_plugs` | SDK name changes from `llama-cpp` to `project-local-inference`; no `plugs` key in workshop.yaml |
| `test_inference_sdk_slots` | Slot key changes to `llama`; assert `slots["llama"]["interface"]` |
| `test_sdk_ordering` | Third entry changes from `llama-cpp` to `project-local-inference` |
| `test_inference_sdk_absent_when_no_inference` | Assert `project-local-inference` absent (not `llama-cpp`) |

## New Tests to Add (`tests/unit/test_config_workshop.py`)

| Test | Asserts |
|------|---------|
| `test_generate_sdk_yaml_with_custom_endpoint` | plug `llama` at `localhost:9000` when `inference_endpoint="192.168.1.5:9000"` |
| `test_generate_sdk_yaml_default_endpoint` | plug `llama` at `localhost:8080` when `inference_endpoint=None` |
| `test_generate_sdk_yaml_returns_empty_no_inference` | empty string when `config.inference is None` |
| `test_omp_agent_sdk_present` | workshop YAML contains `name: omp`, `channel: 14/edge` when `agent="omp"` |
| `test_omp_no_skills_sdk` | no `skills` entry when `agent="omp"` |
| `test_configurable_endpoint_in_system_slot` | system slot endpoint is `192.168.1.5:9000` when `inference_endpoint` set |
| `test_opencode_inference_uses_project_sdk` | `project-local-inference` present for `agent="opencode"` + `inference="llama-cpp"` |
