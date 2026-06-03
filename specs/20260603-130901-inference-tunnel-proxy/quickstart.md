# Quickstart: Inference Tunnel Proxy

**Feature**: `specs/20260603-130901-inference-tunnel-proxy/`
**Date**: 2026-06-03

## Prerequisites

- Workshop installed and functional (`workshop --version`)
- LXD installed and running (`lxc version`)
- llama.cpp server available (for integration testing)

## Init with Inference

```bash
# Create environment with inference tunnel
microjail init myproject --inference llama-cpp --agent opencode
```

**What happens**:
1. `.workshop/myproject.yaml` is generated with a `system` SDK tunnel slot and a `llama-cpp`
   project SDK tunnel plug.
2. `opencode.jsonc` is written with `baseURL: http://localhost:8080/v1`.
3. `.microjail/state.json` is written with `socket_url: http://127.0.0.1:8080/v1`.
4. Workshop launches the environment with the tunnel configured.

## Run with Inference Gate

```bash
# Start your llama.cpp server on the host
llama-server --port 8080 -m model.gguf &

# Run a workload inside the locked container
microjail run -- echo "inference available"
```

**What happens**:
1. Lock severs external egress on the container's primary NIC.
2. The inference gate checks that `localhost:8080` is accepting TCP connections on the host.
3. If the gate passes, the workload spawns inside the locked container.
4. Inside the container, `localhost:8080` is reachable via Workshop's tunnel (not via bind-mount).
5. On workload exit, egress is restored.

## Gate Failure

```bash
# Without llama-server running
microjail run -- echo "no model available"
# Exit code 1, message: "Inference endpoint localhost:8080 is not reachable"
```

## Key Files Changed

| File | Change |
|------|--------|
| `src/microjail/config/workshop.py` | Add system SDK slot + project SDK plug generation when inference is set |
| `src/microjail/gates/inference_socket.py` | Rename to `inference_tunnel.py`; remove UDS paths; TCP-only check |
| `src/microjail/gates/__init__.py` | Update import and call site |
| `src/microjail/commands/init.py` | No functional change (already passes inference to generators) |

## Key Files Unchanged

| File | Reason |
|------|--------|
| `src/microjail/state.py` | `socket_url` already stores HTTP URL |
| `src/microjail/config/opencode.py` | `baseURL` already uses `socket_url` |
| `src/microjail/lxd/network.py` | FR-014: no changes to lock/unlock |
| `src/microjail/config/models.py` | `InferenceBackend` unchanged |
