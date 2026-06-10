## Why

The default Lockdown grants zero capabilities and denies all network egress. There is currently no way for a user to declare a legitimate outbound connection — meaning any workload that needs to reach a host service (an inference endpoint, an MCP server, a GitHub proxy) cannot be run under microjail without manually bypassing the network-egress gate. Endpoint capabilities are the designed mechanism for authorising specific host services through Workshop tunnels; implementing them makes microjail useful for real agent workloads.

## What Changes

- Add `WorkshopEndpointCapability`: a `Capability` implementation that provisions a Workshop tunnel granting workload access to a named host service at `host:port`.
- Add endpoint capability configuration parsing to `.microjail/config.yaml` (type: `endpoint-proxy`, fields: `name`, `endpoint`).
- Wire endpoint capabilities into the `Lockdown` deserialization so they appear alongside gates in config.
- `check()` verifies the tunnel connection exists and the endpoint is reachable from inside the container.
- `provide()` creates the SDK tunnel declaration, refreshes Workshop, and connects plug to slot.
- `revoke()` disconnects and removes the tunnel resources.
- Update `microjail init` to emit an empty `caps` list in the default config scaffold.

## Capabilities

### New Capabilities

- `endpoint-capability`: Provisions, verifies, and revokes a Workshop tunnel that forwards a declared `host:port` into the container under a named plug/slot identifier. This is the only authorised path through the network-egress gate.

### Modified Capabilities

*(none — no existing spec requirements change)*

## Impact

- **New file**: `src/microjail/caps/endpoint.py` — `WorkshopEndpointCapability` struct implementing the `Capability` protocol.
- **Modified**: `src/microjail/caps/__init__.py` — export the new type.
- **Modified**: `src/microjail/microjail.py` — register `WorkshopEndpointCapability` in msgspec decode hook so YAML config deserialises correctly.
- **Modified**: `src/microjail/adapters/workshop.py` — add `connect`, `disconnect`, `tunnel_exists`, and `endpoint_reachable` helpers.
- **New tests**: `tests/unit/test_endpoint_capability.py`, `tests/functional/caps/test_endpoint_capability.py`.
- **No breaking changes** to existing CLI, config schema, or gate interfaces.
