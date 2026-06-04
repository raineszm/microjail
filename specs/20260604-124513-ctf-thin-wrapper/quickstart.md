# Quickstart: CTF Thin Wrapper

**Implementation guide for** `specs/20260604-124513-ctf-thin-wrapper/plan.md`

---

## What changes and why

`ctf/main.py` duplicates microjail's workshop YAML generation and state creation. This refactor moves all config generation into `microjail.config.workshop`, adds `omp` as an agent type, makes the inference endpoint configurable, and adds `workshop connect` to `microjail init`. CTF becomes a thin caller.

---

## Step 1: Extend `EnvironmentConfig` and `AgentHarness`

**`src/microjail/config/models.py`**

```python
# Change:
AgentHarness = Literal["opencode"]
# To:
AgentHarness = Literal["opencode", "omp"]

# Add field (last, with default):
@dataclass(frozen=True)
class EnvironmentConfig:
    name: str
    base_image: str
    inference: InferenceBackend | None
    agent: AgentHarness | None
    inference_endpoint: str | None = None  # NEW: "host:port", None → localhost:8080
```

No existing callers break — `inference_endpoint` has a default.

---

## Step 2: Update `microjail/config/workshop.py`

Add constants and a new function; update the generator.

```python
# New constants (shared by init and ctf)
INFERENCE_PLUG_REF: str = "local-inference:llama"
INFERENCE_SLOT_REF: str = "system:llama"

def generate_sdk_yaml(config: EnvironmentConfig) -> str:
    """Return sdk.yaml for .workshop/local-inference/.

    Returns empty string when config.inference is None.
    """
    if config.inference is None:
        return ""
    endpoint = config.inference_endpoint or "localhost:8080"
    _, sep, port_str = endpoint.rpartition(":")
    if not sep:
        raise ValueError(f"inference_endpoint {endpoint!r} has no port")
    port = int(port_str)
    doc = {
        "name": "local-inference",
        "plugs": {"llama": {"interface": "tunnel", "endpoint": f"localhost:{port}"}},
    }
    buf = io.StringIO()
    yaml.dump(doc, buf)
    return buf.getvalue()
```

In `generate_workshop_yaml`, change the inference block:

```python
# Before
if config.inference is not None:
    provider = config.inference
    sdks.append({"name": provider, "plugs": {provider: {"interface": "tunnel"}}})
    sdks.append({"name": "system", "slots": {provider: {"interface": "tunnel", "endpoint": "localhost:8080"}}})

# After
if config.inference is not None:
    endpoint = config.inference_endpoint or "localhost:8080"
    sdks.append({"name": "project-local-inference"})
    sdks.append({"name": "system", "slots": {"llama": {"interface": "tunnel", "endpoint": endpoint}}})
```

For the agent block, add `omp`:

```python
# Before
if config.agent == "opencode":
    sdks = [{"name": "opencode", "channel": "latest/stable"}, {"name": "skills", "channel": "latest/edge"}]

# After
if config.agent == "opencode":
    sdks = [{"name": "opencode", "channel": "latest/stable"}, {"name": "skills", "channel": "latest/edge"}]
elif config.agent == "omp":
    sdks = [{"name": "omp", "channel": "14/edge"}]
```

---

## Step 3: Update `run_all_gates` gate scope

**`src/microjail/gates/__init__.py`**

```python
# Before
if state.agent is not None:
    results.append(check_config_readonly(workspace))

# After
if state.agent == "opencode":
    results.append(check_config_readonly(workspace))
```

---

## Step 4: Update `microjail init`

**`src/microjail/commands/init.py`**

Add imports:
```python
from microjail.config.workshop import generate_sdk_yaml, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF
from urllib.parse import urlparse
```

Add `--inference-url` flag to `init()`:
```python
inference_url: Annotated[
    str | None,
    typer.Option("--inference-url", help="Inference server URL (e.g. http://192.168.1.5:8080). Scheme and path stripped."),
] = None,
```

Derive `inference_endpoint` from the flag:
```python
inference_endpoint: str | None = None
if inference_url is not None:
    parsed = urlparse(inference_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        _err("--inference-url must start with http:// or https:// and contain a host", code=1)
    inf_port = parsed.port or (443 if parsed.scheme == "https" else 80)
    inference_endpoint = f"{parsed.hostname}:{inf_port}"

socket_url: str | None = f"http://localhost:{inf_port}/v1" if inference else None
config = EnvironmentConfig(
    name=name, base_image=_BASE_IMAGE, inference=inference,
    agent=agent, inference_endpoint=inference_endpoint,
)
```

In `_write_config_files`, add sdk.yaml write:
```python
if config.inference is not None:
    sdk_content = generate_sdk_yaml(config)
    sdk_dir = workspace / ".workshop" / "local-inference"
    try:
        sdk_dir.mkdir(parents=True, exist_ok=True)
        (sdk_dir / "sdk.yaml").write_text(sdk_content)
    except OSError as exc:
        _err(f"Cannot write sdk.yaml: {exc}", code=3)
```

After `_launch_and_verify`, add connect:
```python
if inference is not None:
    try:
        client.connect(name, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF, workspace)
    except RuntimeError as exc:
        _err(str(exc), code=3)
```

Update success print to include sdk.yaml path when inference is set.

---

## Step 5: Update `ctf/main.py`

**Remove**:
```python
from ctf.workshop_config import generate_ctf_workshop_yaml, generate_inference_sdk_yaml
```

**Add**:
```python
from microjail.config.models import EnvironmentConfig
from microjail.config.workshop import (
    generate_workshop_yaml, generate_sdk_yaml,
    INFERENCE_PLUG_REF, INFERENCE_SLOT_REF,
)
from microjail.state import EnvironmentState
```

**Replace workshop YAML generation:**
```python
# Before
yaml_content = generate_ctf_workshop_yaml(env_name, inference_host, inference_port)
(workshop_dir / f"{env_name}.yaml").write_text(yaml_content)
sdk_dir = workshop_dir / "local-inference"
sdk_dir.mkdir(exist_ok=True)
(sdk_dir / "sdk.yaml").write_text(generate_inference_sdk_yaml(inference_port))

# After
config = EnvironmentConfig(
    name=env_name,
    base_image="ubuntu@24.04",
    inference="llama-cpp",
    agent="omp",
    inference_endpoint=f"{inference_host}:{inference_port}",
)
(workshop_dir / f"{env_name}.yaml").write_text(generate_workshop_yaml(config))
sdk_dir = workshop_dir / "local-inference"
sdk_dir.mkdir(exist_ok=True)
(sdk_dir / "sdk.yaml").write_text(generate_sdk_yaml(config))
```

**Replace manual state dict:**
```python
# Before
state_doc = {**_STATE_JSON_TEMPLATE, "name": env_name, "created_at": datetime.now(UTC).isoformat()}
(microjail_dir / "state.json").write_text(json.dumps(state_doc, indent=2))

# After
state = EnvironmentState(
    name=env_name,
    base_image="ubuntu@24.04",
    inference="llama-cpp",
    agent="omp",
    socket_url=f"http://localhost:{inference_port}/v1",
    created_at=datetime.now(UTC),
)
state.to_json(workspace)
```

**Replace inline connect strings:**
```python
# Before
workshop_client.connect(env_name, "local-inference:llama", "system:llama", workspace)

# After
workshop_client.connect(env_name, INFERENCE_PLUG_REF, INFERENCE_SLOT_REF, workspace)
```

---

## Step 6: Delete `ctf/workshop_config.py` and its tests

```bash
rm ctf/workshop_config.py
rm tests/unit/test_ctf_workshop_config.py
```

---

## Step 7: Update `tests/unit/test_config_workshop.py`

**Update `_full_config()`** to include `inference_endpoint`:
```python
def _full_config() -> EnvironmentConfig:
    return EnvironmentConfig(
        name="myproject",
        base_image="ubuntu@26.04",
        inference="llama-cpp",
        agent="opencode",
        inference_endpoint="localhost:8080",
    )
```

**Update existing assertions** (see data-model.md for the full list of 6 tests).

**Add new test helpers and tests** for `generate_sdk_yaml`, `omp` agent, and configurable endpoint (7 new tests — see data-model.md).

---

## Verification checklist

```bash
uv run pytest tests/unit/test_config_workshop.py -v      # all 6 updated + 7 new tests pass
uv run pytest tests/unit/test_ctf_main.py -v             # CTF main still works
uv run pytest tests/unit/test_gates_inference_tunnel.py -v  # gate scope change
uv run pytest tests/unit/ -v                             # full unit suite green
```

Ensure `test_ctf_workshop_config.py` no longer exists and is not imported anywhere.
