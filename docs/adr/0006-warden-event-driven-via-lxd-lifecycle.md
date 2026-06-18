# Warden is event-driven via LXD lifecycle events

The Warden is the runtime supervisor for a workload under an applied Lockdown. Until this change it polled each gate and capability on a fixed interval (default one second) and called each one's `check()` method. The new Warden subscribes to LXD `lifecycle` events for the workload's container and re-validates gate configuration on each event, with a self-healing re-snapshot on every WebSocket (re)connect. The behavioral probes — most notably the `network-egress` gate's `bash -c ": >/dev/tcp/1.1.1.1/443"` — are removed. Capabilities are no longer monitored at runtime; their checks happen once at launch.

## Status

Accepted.

## Context

The polling model had three problems.

1. **LXD is the source of truth.** Gates are enforced by LXD configuration (e.g. removing all NICs from the workshop container). The only way a gate can be violated during execution is if the LXD configuration changes — by a host user, an admin tool, or a programmatic API call. A workload process inside the container cannot modify LXD configuration. The behavioral probes were redundant with LXD's enforcement.
2. **The behavioral probes were wrong.** The egress probe tested a single endpoint (1.1.1.1:443) and required bash inside the container. If the container's shell was not bash (alpine, distroless, scratch), the exec failed and `check()` returned `False` — which the Warden read as a violation. The error path conflated "tool not found" with "egress exists," and the probe terminated perfectly-sealed minimal workloads. The ten-second timeout on a confirmed-blocked path was also slow.
3. **Polling was wasteful.** At a one-second interval the loop asked "did anything change?" constantly when the answer was almost always "no." Idle CPU and unnecessary container introspection on a stable workload.

The polling model also conflated two concerns. Capability checks were framed as runtime monitoring, but a capability is about authorization, not liveness: a tunnel that is connected but pointing to a dead upstream service is not a policy violation — the policy is being honored, the service is just down. Behavioral probes on capabilities at runtime are quality-of-service signals, not security signals.

## Decision

The Warden is restructured around LXD lifecycle events. A new `LxdEventWatcher` class in `src/microjail/adapters/lxd_events.py` owns the WebSocket subscription to `GET /1.0/events?type=lifecycle`, client-side filters by `metadata.name == <container>` and `metadata.project == <lxd_project>`, and pushes matching events onto a `queue.Queue`. A reader thread inside the watcher handles the WebSocket I/O so the Warden stays single-threaded.

The Warden's main loop uses `process.wait(timeout=0.1)` and drains the event queue on each `TimeoutExpired`. On a non-empty drain, it re-snapshots the instance via `lxc_instance()` and re-runs every gate's `check()`. The first failure terminates the workload and raises `GatePolicyViolation` (exit code `RUNTIME_GATE_POLICY_VIOLATION`).

On every successful (re)connect — initial *and* reconnects — the watcher pushes a `"reconnect"` sentinel onto the queue. The Warden treats it identically to any other event: re-snapshot and re-validate. This is the self-healing property: events lost during a disconnect window are harmless because the next connect re-validates against current LXD state.

Reconnect policy is three attempts at 0.3s, 0.5s backoff (0.8s total budget). Three failures raise `LxdEnforcementLost`, which the Warden escalates as `GatePolicyViolation` and terminates the workload. The escalation path is `LxdEnforcementLost → terminate_workload() → RUNTIME_GATE_POLICY_VIOLATION`.

The protocol is extended:

- `Gate.check(mj) -> bool` is now the **config check** (instance state matches invariant).
- `Gate.verify(mj) -> bool` is the **behavioral probe**. Required by the protocol; concrete gates with no behavioral aspect implement it as `return True`.
- `Capability.check(mj) -> bool` is the **config check** (e.g. tunnel connected in the Workshop SDK).
- `Capability.verify(mj) -> bool` is the **behavioral probe** (e.g. TCP reachability to host endpoint). Required by the protocol; concrete capabilities with no behavioral aspect implement it as `return self.check(self)`.
- The Warden calls `check()` only, and only on gates. The new `MicroJail.pre_launch_verify()` method calls `verify()` on every gate and every capability. It is invoked by `exec`, `shell`, and `lock`.

The `network-egress` gate's behavioral probe is removed. `NetworkDrop.check()` becomes "no devices of `type: nic` in `expanded_devices`" — a config check. `NetworkDrop.verify()` returns `True`. The `readonly-config` gate's `check()` is already a config check (it reads `expanded_devices` for the `microjail-config-ro` device with `readonly=true`) and is unchanged; its `verify()` returns `True`.

The `fatal: bool` flag on capabilities is repurposed from a runtime knob to a launch-time knob. A `fatal` capability whose `verify()` fails at launch blocks the launch (exit `FATAL_RUNTIME_CAPABILITY_VIOLATION`); a non-fatal failure is reported as a warning and the workload proceeds. The warden's loop no longer touches capabilities.

## Consequences

**Positive**

- The Warden is silent at idle: zero syscalls on a stable workload instead of one per second.
- The bash-dependency bug in the egress probe is gone. Minimal container images (alpine, distroless) no longer trigger false-positive gate violations.
- The disconnect window is bounded (0.8s reconnect budget) and re-validated on every reconnect. Drift introduced during the window is caught at the next successful snapshot.
- Capabilities are now liveness-checked only at launch, which matches their actual semantic — authorization, not liveness.
- The protocol now has a clean split between `check()` (config) and `verify()` (behavioral), with the call sites making the split explicit.

**Negative**

- The Warden requires a working LXD event subscription. LXD daemon restarts during a workload's lifetime (typically 5–10s) will exceed the 0.8s reconnect budget and trigger an escalation. Workloads that routinely outlive LXD restarts will see false-positive terminations. This is a deliberate security-over-availability trade-off: the alternative (loop forever) lets a workload run unsupervised during a multi-hour LXD outage.
- The disconnect window is also a blind window. A host-side `lxc config device add` during a 0.8s reconnect is not detected until the next event or the next successful reconnect. Mitigation: the `"reconnect"` sentinel re-validates on each successful reconnect, so any drift is caught within 0.8s plus reconnect time.
- Capability violations can no longer be detected at runtime. If a Workshop-side operation disconnects a tunnel after launch, the Warden does not notice until the workload exits. The `pre_launch_verify()` step captures upstream liveness at the moment of launch; runtime capability liveness is now an external concern.
- A new module (`adapters/lxd_events.py`) is introduced, along with an async WebSocket dependency (`websockets`). The `Warden.supervise()` loop, the `LxdEventWatcher`, the `Gate` and `Capability` protocols, every concrete gate and capability, and the relevant test suite all change.

**Reversibility**

Moderate. Restoring the polling loop is a single-method change in `Warden.supervise()` (replace the event-queue drain with a fixed-interval `check_policies()`). Restoring the egress probe requires re-implementing `NetworkDrop.verify()` as the `bash`/`python3` exec and re-evaluating the `commands/cap.py` `is_locked` check against the new protocol. The protocol change is additive — the old single-`check` shape can be re-derived by treating `verify() = check` everywhere.

## Note on ADR numbering

`docs/adr/` already contains two `0005-*` files (`0005-endpoint-capability-cli-declaration-application.md` and `0005-microjail-config-runtime-seam.md`). The collision is a pre-existing condition unrelated to this change. This ADR uses `0006` to continue the higher of the two conflicting numbers; renumbering the existing `0005-microjail-config-runtime-seam.md` to `0006` is a separate housekeeping task.
