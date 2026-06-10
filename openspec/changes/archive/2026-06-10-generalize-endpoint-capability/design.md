## Context

`WorkshopEndpointCapability` currently uses a single `endpoint: str` field for both the host-side address (where the service runs, used by the system slot) and the container-side address (what the workload connects to, written to the plug). Workshop tunnels forward from the system slot endpoint to the plug endpoint — when the host service binds to an interface address that differs from what the container should use, or when a port remap is needed, a single field is insufficient.

The Workshop tunnel model: the system slot declares where traffic originates on the host; the plug declares what the container-side SDK connects to. They need not be identical — Workshop resolves the forwarding independently.

## Goals / Non-Goals

**Goals:**
- Split `endpoint` into `host_endpoint` (system slot) and `container_endpoint` (plug), allowing them to differ.
- `container_endpoint` defaults to `host_endpoint` when not specified, preserving the common case.
- `check()` verifies reachability against `container_endpoint` from inside the container.
- Update config deserialization to parse the new fields.
- Update all tests and call sites.

**Non-Goals:**
- Backward compatibility for the `endpoint` field name in config. This is a **BREAKING** rename: `endpoint` → `host_endpoint`.
- Support for tunnel types other than `host:port`.
- Changing the Workshop adapter interface shape beyond what's needed for the new fields.
- Per-field validation of `host_endpoint` vs `container_endpoint` format (both remain opaque `host:port` strings).

## Decisions

### 1. Field names: `host_endpoint` and `container_endpoint`

```yaml
caps:
  - type: endpoint-proxy
    name: inference
    host_endpoint: 127.0.0.1:8080       # where the service runs on the host
    container_endpoint: 10.0.0.1:8080    # optional; defaults to host_endpoint
```

`host_endpoint` is written to the system slot (where traffic originates on the host). `container_endpoint` is written to the plug (what the workload connects to inside the container). The names are explicit about which side they describe.

**Alternative considered:** `endpoint` + `container_endpoint` (keep `endpoint` and add optional override). Rejected: having `endpoint` mean "host endpoint" while `container_endpoint` means "container endpoint" is asymmetric and confusing. Two explicitly-named fields with one defaulting to the other is clearer.

**Alternative considered:** `source` / `target`. Rejected: too abstract; "host" and "container" are well-understood terms in this codebase.

### 2. Default: `container_endpoint` defaults to `host_endpoint`

`container_endpoint` is typed `str | None = None`. At every use site, the resolved value is `self.container_endpoint if self.container_endpoint is not None else self.host_endpoint` — an explicit `None`-check rather than `or`, to avoid silently swallowing an empty string (which `msgspec` can deserialize as `""` from YAML). This avoids needing `__post_init__` (which complicates msgspec deserialization) and keeps the struct's serialized form honest (an explicit `null` in YAML means "use default").

Config without `container_endpoint`:
```yaml
- type: endpoint-proxy
  name: inference
  host_endpoint: localhost:8080
```
Behaves identically to the old `endpoint: localhost:8080` — both sides use the same address.

**Alternative considered:** `msgspec.field(default_factory=...)` with `__post_init__`. Rejected: `default_factory` cannot reference sibling fields; `__post_init__` works but complicates `msgspec.convert()` during deserialization.

### 3. `check()` verifies `container_endpoint`, not `host_endpoint`

The reachability probe runs from inside the container via `workshop exec`. It must test the address the workload will actually use, which is `container_endpoint`. The host-side address may be unreachable from inside the container (e.g., host binds `127.0.0.1` which is not the container's loopback).

The connection existence check (parsing `workshop connections` output) is unchanged — the tunnel row still uses `<name>` as the plug/slot identifier.

### 4. Config deserialization: break `endpoint`, no backwards compat

The `dec_hook` maps `type: endpoint-proxy` → `msgspec.convert(obj, type=WorkshopEndpointCapability)`. The struct's field rename (`endpoint` → `host_endpoint`) means existing configs with `endpoint:` will fail deserialization with a clear msgspec error about unknown fields. This is intentional — the change is **BREAKING** and the error guides the user to rename the field.

**Alternative considered:** accept `endpoint` as an alias in `dec_hook`, mapping it to `host_endpoint` before deserialization. Rejected: adds permanent complexity to the decode path for a one-time migration. The field rename is trivial for users (`sed 's/endpoint:/host_endpoint:/'`) and a clean break is simpler to maintain.

### 5. Workshop adapter: `add_tunnel_plug` and `add_tunnel_slot` take distinct endpoints

`add_tunnel_plug` receives `container_endpoint` (or resolved default). `add_tunnel_slot` receives `host_endpoint`. Both already accept an `endpoint` parameter; no signature change needed at the adapter level — the caller splits the fields before passing them.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| Existing configs break on upgrade | Clear error from msgspec; documented as BREAKING in release notes |
| User forgets to set `container_endpoint` when needed | Behavior is identical to before (same address for both sides); only users who need the split must configure it |
| `container_endpoint` null in serialized form confusing | `is not None`-based resolution is simple and predictable; documented in field docstring |
| `check()` probes wrong endpoint during migration | Probe address comes from `container_endpoint` field; if not set, equals `host_endpoint` (identical to old behavior) |

## Migration Plan

1. Rename `endpoint:` → `host_endpoint:` in all `.microjail/config.yaml` files.
2. Optionally add `container_endpoint:` where the container-side address differs.
3. No rollback needed — if `container_endpoint` is omitted, behavior is identical to pre-change.
