## Context

The current microjail implementation conflates configuration alignment checks with behavioral/reachability verification inside the `check()` method of the `Gate` and `Capability` protocols. Specifically:
- `NetworkDrop.check()` runs a bash egress probe inside the container. This causes high CPU usage when polled periodically and fails on minimal/distroless/alpine images lacking `bash`.
- `WorkshopEndpointCapability.check()` performs a TCP reachability check inside the container on every poll, which is heavy and conflates authorization/tunnels with host service health.

To address this, we need to split configuration checks from behavioral verification. `check()` will only query the configuration state using local command-line clients (e.g. `lxc` query and `workshop connections`), while a new `verify()` method will handle the behavioral verification. Verification will run once at launch-time (pre-launch) rather than periodically at runtime.

## Goals / Non-Goals

**Goals:**
- Add `verify()` method to the `Gate` and `Capability` protocols.
- Narrow `check()` methods to lightweight, configuration-only checks.
- Implement `MicroJail.pre_launch_verify()` to run all behavioral verifications at workload start.
- Integrate pre-launch verification into `lock`, `exec`, and `shell` commands, mapping failures to the correct exit codes (68 for gates, 66 for capabilities) or warning messages.
- Ensure all queries against LXD use the existing `lxc` command-line client (`lxc query` via `lxc_instance()`).

**Non-Goals:**
- Changing the Warden loop from polling to event-driven (this is a future change).
- Removing the runtime polling check loop (it continues to poll `check()`, which is now config-only).
- Modifying how capabilities are applied/revoked at runtime.

## Decisions

### Decision 1: Use `lxc` CLI client via `microjail.lxc_instance()` for NetworkDrop configuration checks
- **Rationale**: To verify network isolation without executing probes inside the container, we query the container's devices. Calling `microjail.lxc_instance().devices` uses the `lxc query` subprocess under the hood, adhering to the constraint of using the `lxc` client.
- **Alternatives Considered**: Direct WebSocket or REST API connection to LXD daemon. This was rejected to avoid adding raw socket or cert management dependencies, and to leverage existing helper methods.

### Decision 2: Return `VerificationResult.UNSUPPORTED` for gates/capabilities that have no behavioral probe
- **Rationale**: Gates like `ReadonlyConfig` and `NetworkDrop` have their primary enforcement checked by `check()`. To allow uniform iteration in `pre_launch_verify()`, they implement `verify()` returning `VerificationResult.UNSUPPORTED`. This distinguishes them from gates that did perform a behavioral probe and reported `VERIFIED` or `FAILED`, and lets the CLI surface them as a "Note: Verification not supported for {name}" line on stdout.
- **Alternatives Considered**: Returning `True` (would be indistinguishable from a real pass) or omitting the method (would force `hasattr` checks in iteration logic). Rejected: protocol consistency plus the three-valued `VerificationResult` enum (`VERIFIED` / `FAILED` / `UNSUPPORTED`) gives both uniform iteration and honest reporting.

### Decision 3: Run `pre_launch_verify` at launch-time only
- **Rationale**: Behavioral probes (such as TCP connection checks) are relatively slow and resource-intensive. Running them on a periodic loop wastes CPU. Running them at launch-time guarantees that everything is fully functional when the workload starts.
- **Alternatives Considered**: Keep running behavioral checks on the Warden polling loop. Rejected because it defeats the purpose of dropping idle CPU usage and removing the dependency on in-container tools at runtime.

## Risks / Trade-offs

- **[Risk]** If the `lxc` client command fails due to transient environment issues, `NetworkDrop.check()` might return `False` and trigger a false-positive violation.
  - *Mitigation*: Ensure `check()` catches all command exceptions and returns `False` safely, while using robust timeouts and logging where possible.
- **[Risk]** Capability verification might fail if the host service is slow to startup.
  - *Mitigation*: The `verify()` check runs after the capability is provided and before the workload execution begins, giving a stable window.

## Migration Plan

1. **Protocol Update**: Add `verify(self, microjail: MicroJail) -> bool` to `Gate` and `Capability` protocols.
2. **Implementation Update**:
   - Update `NetworkDrop`: narrow `check()` to check for NICs in `expanded_devices`, add `verify()` returning `True`.
   - Update `ReadonlyConfig`: add `verify()` returning `True`.
   - Update `WorkshopEndpointCapability`: narrow `check()` to verify connection presence in `workshop connections` output; add `verify()` doing TCP reachability check.
3. **Pre-Launch Verify Integration**:
   - Implement `pre_launch_verify` on `MicroJail` to verify all gates (raising `GateError`) and capabilities (raising `CapabilityError` if fatal, warning if non-fatal).
   - Integrate into `lock.py`, `exec.py`, and `shell.py`.
4. **Verification**: Update unit/functional tests to assert configuration checks are config-only, `verify` performs behavioral checks, and `pre_launch_verify` fails or issues warnings correctly.

## Open Questions

None.
