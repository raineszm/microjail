## Why

The current `WorkshopEndpointCapability` uses a single `endpoint` field for both the host-side address (where the service actually runs) and the container-side address (what the workload sees). This forces them to be identical, which breaks when the host service binds to a specific interface address that differs from what the container's network namespace should use (e.g., host binds `127.0.0.1:8080` but the container must reach it via the Workshop tunnel at `10.0.0.1:8080`, or a port remap is needed).

## What Changes

- **BREAKING**: Rename `endpoint` field to `host_endpoint` in `WorkshopEndpointCapability` — the address of the service on the host, used by the Workshop tunnel's system-side slot to forward traffic.
- Add `container_endpoint` field — the address the workload uses inside the container. This goes into the plug declaration (in-project SDK) so the workload connects to it.
- `container_endpoint` defaults to `host_endpoint` when omitted, preserving the common case where they are identical.
- Config field renamed: `endpoint` in YAML is now `host_endpoint`; optional `container_endpoint` field added. Old configs with `endpoint:` will fail deserialization with a clear error (no backwards-compat aliasing).
- `check()` verifies reachability from inside the container against `container_endpoint` (not `host_endpoint`).
- All callsites updated to use the new field names.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `endpoint-capability`: The `endpoint` field is split into `host_endpoint` and `container_endpoint`. The plug declaration writes `container_endpoint`; the slot declaration writes `host_endpoint`. `check()` tests reachability against `container_endpoint`.

## Impact

- `src/microjail/caps/endpoint.py` — struct fields, `check()`, `provide()`, `revoke()`
- `src/microjail/microjail.py` — `TaggedCapability` union type (imports the struct; `dec_hook` itself needs no change)
- `tests/unit/test_endpoint_capability.py` — all constructor calls and YAML fixtures
- `tests/unit/test_cap_contract.py` — capability construction
- `tests/functional/caps/test_endpoint_capability.py` — cap helper and test cases
- `tests/functional/commands/test_config_schema.py` — YAML fixture and assertions
- `tests/e2e/test_endpoint_capability.py` — constructor calls
- User configs (`.microjail/config.yaml`) — `endpoint` field renamed; `container_endpoint` optionally added
- `openspec/specs/endpoint-capability/spec.md` — references to `endpoint` and `self.endpoint` updated to new field names
