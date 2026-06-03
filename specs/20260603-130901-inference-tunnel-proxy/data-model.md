# Data Model: Inference Tunnel Proxy

**Feature**: `specs/20260603-130901-inference-tunnel-proxy/`
**Date**: 2026-06-03

## Overview

This feature modifies two data shapes:

1. **`workshop.yaml`** — gains a system SDK entry with a tunnel slot and a project SDK entry with
   a corresponding tunnel plug when `--inference llama-cpp` is specified.
2. **Gate module** — `inference_socket.py` is renamed to `inference_tunnel.py` and the UDS check
   is replaced with a TCP reachability check.

The `EnvironmentState` dataclass and `state.json` are **unchanged** — `socket_url` already stores
an HTTP URL (`http://127.0.0.1:8080/v1`) and `inference` already stores `"llama-cpp"`.

---

## Workshop YAML Schema — With `--inference llama-cpp`

```yaml
name: myproject
base: ubuntu@26.04
sdks:
  - name: opencode
    channel: latest/stable
  - name: skills
    channel: latest/edge
  - name: llama-cpp
    plugs:
      llama-cpp:
        interface: tunnel
  - name: system
    slots:
      llama-cpp:
        interface: tunnel
        endpoint: localhost:8080
```

**Fields**:
- `name`: from `EnvironmentConfig.name`.
- `base`: from `EnvironmentConfig.base_image`.
- `sdks[0]` (`opencode`): included when `--agent opencode`.
- `sdks[1]` (`skills`): included alongside `opencode`.
- `sdks[2]` (`llama-cpp`): the project SDK for inference. Only present when `--inference llama-cpp`.
  - `plugs.llama-cpp.interface`: always `"tunnel"`.
  - Name derived from `config.inference` value.
- `sdks[3]` (`system`): the system SDK. Only present when `--inference llama-cpp`.
  - `slots.llama-cpp.interface`: always `"tunnel"`.
  - `slots.llama-cpp.endpoint`: host-side address for the inference server (e.g., `localhost:8080`).
  - Name `llama-cpp` matches the inference provider value.

**Ordering**: The system SDK and inference project SDK entries appear after `opencode` and `skills`
(FR-012). This makes the file human-readable: user-facing SDKs first, infrastructure SDKs last.

## Workshop YAML Schema — Without `--inference`

```yaml
name: myproject
base: ubuntu@26.04
sdks:
  - name: opencode
    channel: latest/stable
  - name: skills
    channel: latest/edge
```

No `system` SDK, no `llama-cpp` project SDK, no tunnel entries. Identical to the pre-feature output.

## Workshop YAML Schema — Bare (no `--agent`, no `--inference`)

```yaml
name: myproject
base: ubuntu@26.04
sdks: []
```

No SDKs at all. `system` SDK is only present when inference is enabled.

---

## Gate Module: `inference_tunnel.py`

The gate function signature changes from:

```python
def check_inference_socket(socket_url: str | None) -> GateResult:
```

to:

```python
def check_inference_tunnel(socket_url: str | None) -> GateResult:
```

**Removed**:
- `_UDS_SCHEMES` constant
- `_extract_socket_path()` function
- `_check_uds()` function
- The `_check_tcp` dispatch in `check_inference_socket`

**Retained**:
- `_parse_tcp_host_port()` function
- `_check_tcp()` function (renamed context: now the primary path, not a fallback)

**Added**:
- The function directly calls `_check_tcp()` when `socket_url` is not `None`.

The gate name in `GateResult` changes from `"inference-socket"` to `"inference-tunnel"`.

---

## `gates/__init__.py` — `run_all_gates`

The call site in `run_all_gates` changes from:

```python
from microjail.gates.inference_socket import check_inference_socket
...
result = check_inference_socket(state.socket_url)
```

to:

```python
from microjail.gates.inference_tunnel import check_inference_tunnel
...
result = check_inference_tunnel(state.socket_url)
```

No other changes.

---

## `config/workshop.py` — `generate_workshop_yaml`

The function signature extends to accept `inference`:

```python
def generate_workshop_yaml(config: EnvironmentConfig) -> str:
```

The `EnvironmentConfig.inference` field (already present, already `"llama-cpp" | None`) drives
the conditional generation of:
- A `system` SDK entry with `slots.{provider_name}` containing `interface: tunnel` and
  `endpoint: localhost:{port}`.
- A project SDK entry named `{provider_name}` with `plugs.{provider_name}` containing
  `interface: tunnel`.

The default endpoint for `llama-cpp` is `localhost:8080`, derived from the `_SOCKET_URL` constant
in `init.py` (host and port portion only, stripping the `/v1` path).

---

## State — Unchanged

`EnvironmentState` and `.microjail/state.json` require **no changes**. The existing fields already
support this feature:

- `inference: "llama-cpp" | None` — used to conditionally generate the tunnel entries.
- `socket_url: "http://127.0.0.1:8080/v1" | None` — used by the gate for TCP reachability checks
  and by `opencode.jsonc` generation for the `baseURL`.
