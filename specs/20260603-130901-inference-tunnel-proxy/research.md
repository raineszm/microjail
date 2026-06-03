# Research: Inference Tunnel Proxy

**Feature**: `specs/20260603-130901-inference-tunnel-proxy/`
**Date**: 2026-06-03

## Resolution of NEEDS CLARIFICATION Items

No unresolved NEEDS CLARIFICATION markers in the spec. All items were resolved during the
clarification session.

## Research Findings

### 1. Workshop Tunnel Interface YAML Structure

**Decision**: The `system` SDK entry contains only `slots` (no `plugs`); the project SDK entry
contains only `plugs` (no `slots`). The slot and plug are both named after the inference provider.

**Rationale**: Workshop's plug/slot model follows the Snaps convention where slots provide and
plugs consume. The system SDK provides host-level connectivity (a slot); the project SDK consumes
it (a plug). Including `plugs` on the system SDK was an artefact of the example `tmp/workshop.yaml`
that was incorrect.

**Alternatives considered**:
- Both `plugs` and `slots` on the system SDK (rejected: incorrect per Workshop convention)
- Generic names like `inference-slot` (rejected: user specified naming after the provider)

**Example YAML for `--inference llama-cpp --agent opencode`**:

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

### 2. Workshop Tunnel Mechanics During Lock

**Decision**: Modify `lock_egress` and `unlock_egress` to enumerate ALL LXD devices whose type
contains `"nic"` and clear/restore routes on each. The existing `_nic_device()` helper that
finds only the first NIC is replaced with `_all_nic_devices()` that returns all NICs.

**Rationale**: Clearing routes on only the first NIC is insufficient if the container has
multiple network interfaces (e.g., a second NIC for internal networking). Enumerating all NICs
ensures complete egress severance. The tunnel survives because it is a non-NIC device and is
not in the enumeration.

**Alternatives considered**:
- Remove all network devices entirely (rejected: would destroy the tunnel, making inference
  unreachable during lock — defeating the feature's purpose)
- Add iptables rules instead of route clearing (rejected: beyond scope, existing approach works)

### 3. Inference Gate TCP Check Implementation

**Decision**: Replace the UDS socket check with a TCP connection attempt to the host-side port
extracted from `state.socket_url`. Use `socket.create_connection()` with a 5-second timeout.

**Rationale**: The existing `inference_socket.py` already has a `_check_tcp()` function that
performs exactly this check. The UDS code path (`_check_uds()`, `_extract_socket_path()`, and
`_UDS_SCHEMES`) must be removed, leaving only the TCP path.

**Alternatives considered**:
- HTTP HEAD request to `/v1/models` (rejected: over-engineering for a reachability check;
  the gate's job is "can I connect?", not "can I chat?")
- Check that `socket_url` starts with `http://` (rejected: passive validation, not a reachability check)

### 4. Naming Convention for Slot/Plug/SDK

**Decision**: All three (project SDK name, system slot name, project plug name) use the inference
provider value as their name (e.g., `llama-cpp` for `--inference llama-cpp`).

**Rationale**: Direct, discoverable naming that self-documents the connection. For a future
`--inference foo-bar`, they would all be named `foo-bar`.

**Alternatives considered**:
- A generic `inference` name (rejected: user explicitly asked for provider-related naming)
- A `se-` prefix like the original example `se-llama` (rejected: no prefix convention needed)

### 5. Module Rename: `inference_socket.py` → `inference_tunnel.py`

**Decision**: Rename the gate module from `inference_socket` to `inference_tunnel` to reflect
the pivot from UDS to TCP tunnel. Update the gate name in `GateResult` from `inference-socket`
to `inference-tunnel`.

**Rationale**: The module name `inference_socket` implies UDS sockets, which is no longer the
mechanism. The gate now checks TCP reachability through a Workshop tunnel. The name should
match the reality.

**Alternatives considered**:
- Keep `inference_socket.py` and change internals only (rejected: misleading module name;
  Constitution III mandates names that describe intent)
### 6. Workshop Tunnel Device Type Verification

**Finding**: The Workshop tunnel interface is a separate LXD device created by `workshop launch`,
distinct from NIC-type devices.

**Evidence**:
- `lock_egress()` in `src/microjail/lxd/network.py` uses `_nic_device()` which searches for the
  first LXD device whose type contains `"nic"`. This is being changed to enumerate ALL NICs.
- The tunnel device is created by Workshop based on the `workshop.yaml` plug/slot declarations;
  it is not created or managed by microjail code.
- The tunnel is not a NIC-type device, so it is not in the enumeration.

**Implication**: The tunnel device survives the lock operation because it is not a NIC-type device
and is not in the enumeration. `lock_egress` is modified to clear routes on ALL NICs, making the
lock more thorough while preserving the tunnel.
