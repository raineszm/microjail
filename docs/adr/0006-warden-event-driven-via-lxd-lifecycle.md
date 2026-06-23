# 0006 Warden is event-driven via LXD lifecycle events

The Warden is the runtime supervisor for a workload under an applied Lockdown. It previously polled each gate and capability on a fixed interval (default one second) and called each one's `check()` method. The new Warden subscribes to LXD `lifecycle` events for the workload's container via `lxc monitor` and re-validates gate configuration on each event. Behavioral probes — most notably the `NetworkDrop` gate's `bash -c ": >/dev/tcp/1.1.1.1/443"` egress probe — are removed. Capabilities are no longer monitored at runtime; their checks happen once at launch.

## Considered Options

- **Polling loop (status quo).** Fixed-interval inspection of all gates and capabilities. Simpler, but wasteful on stable workloads, requires a bash-dependent egress probe that false-positives on minimal container images (alpine, distroless), and conflates authorization with liveness for capabilities.
- **Event-driven via raw LXD WebSocket.** A `websockets`-based client connecting to `GET /1.0/events?type=lifecycle` directly. Lower latency, but requires managing LXD client certs, the TLS handshake, socket discovery, and a new pip dependency (`websockets`). Introduces a new transport paradigm into a codebase that shells out to `lxc` for every other LXD interaction.
- **Event-driven via `lxc monitor` subprocess.** Uses the system `lxc` CLI's built-in event streaming command. No new dependencies, no cert or socket management (the CLI handles auth), consistent with the rest of the codebase's `subprocess.run(["lxc", ...])` pattern. The subprocess constructor is injected so tests can supply a stub.
- **Reconnect with bounded backoff on event-feed loss.** Three attempts at 0.3s/0.5s (0.8s total budget) before escalating. Absorbs transient LXD blips but introduces a window of unsupervised execution where a malicious host could make an LXD configuration change that the Warden cannot detect.
- **No reconnect — immediate escalation on event-feed loss.** Every subprocess exit is a gate violation. No reconnect budget, no backoff, no retry. Terminates the workload immediately.

## Decision

We chose the `lxc monitor` subprocess (not a raw WebSocket) with no reconnect (immediate escalation), plus a `"reconnect"` sentinel on initial start, and a `check()`/`verify()` protocol split that moves capabilities out of the runtime loop entirely.

**Transport: `lxc monitor` subprocess.** `LxdEventWatcher` spawns `lxc monitor --type=lifecycle --format=json --quiet --project=<lxd_project> --force-local` and consumes its stdout line-by-line. Three properties drive this: (1) no cert handling — the `lxc` CLI already authenticates; (2) no socket management — the CLI handles the local Unix socket or remote connection; (3) consistency — every other LXD interaction in microjail shells out to `lxc`.

**No reconnect.** When the `lxc monitor` subprocess exits for any reason (LXD daemon stop, SIGHUP, `lxc` binary crash, terminal readline error, OOM kill), `LxdEventWatcher` raises `LxdEnforcementLost` immediately. The Warden catches it, terminates the workload, and escalates as `GatePolicyViolation` (exit code 84). Under the threat model "LXD is the only thing that can enforce," a workload whose event feed has died is a workload we cannot supervise — and that is a security regression. The cost is that any LXD daemon restart terminates running workloads; users of long-lived workloads accept that trade-off.

**Sentinel on initial start.** On the initial successful start of the `lxc monitor` subprocess, the watcher pushes the literal string `"reconnect"` onto the queue. The Warden treats it identically to any other event: re-snapshot the instance and re-validate every gate. This closes the brief window between lockdown application and the first real `instance-updated` event. Without it, a stable workload with no LXD configuration changes would never trigger a re-validation. The sentinel is emitted exactly once per watcher instance; because there is no reconnect, it is never re-emitted.

**Protocol split: `check()` / `verify()`.** Every `Gate` and `Capability` exposes `check(mj) -> bool` (config-state) and `verify(mj) -> bool` (behavioral). The Warden calls `check()` only, and only on gates. `MicroJail.pre_launch_verify()` calls `verify()` on every gate and capability. `NetworkDrop.check()` becomes a config check (no devices of `type: nic` in `expanded_devices`); its behavioral probe is dropped. `WorkshopEndpointCapability.check()` becomes a tunnel-state check; `verify()` performs the TCP reachability probe.

**Capabilities are launch-time only.** The Warden no longer monitors capabilities at runtime. A capability that disappears mid-workload is not detected. `pre_launch_verify()` captures liveness at launch; the `fatal: bool` flag is repurposed from a runtime knob to a launch-time knob (fatal failure blocks launch; non-fatal failure is a warning).

## Consequences

**Positive**

- Idle CPU drops to zero on stable workloads (no per-second polling).
- The bash-dependency bug is eliminated. Minimal containers (alpine, distroless) no longer trigger false-positive gate violations.
- No new pip dependency. The watcher uses the system `lxc` CLI; no cert or socket management code is added.
- The protocol now has a clean split between config-state (`check()`) and behavioral (`verify()`), with each call site using the right one.
- Capability liveness is checked at the semantically meaningful point (launch), not continuously during execution where it conflates authorization with availability.
- No new exit codes. `pre_launch_verify` failures reuse `GATE_APPLICATION_FAILURE` (68) and `CAPABILITY_APPLICATION_FAILURE` (66).

**Negative**

- Any LXD daemon restart, `lxc` binary crash, or OOM kill of the `lxc monitor` process terminates running workloads. A 5–10s LXD restart for a routine upgrade will kill every supervised workload. This is a deliberate security-over-availability trade-off.
- A brief blind window exists between `lxc monitor` startup and the sentinel reaching the Warden (a few milliseconds). A host-side `lxc config device add` during this window is not detected until the sentinel triggers re-validation.
- Capability liveness is not monitored at runtime. A Workshop-side tunnel disconnect after launch goes unnoticed until the workload exits or the user runs `microjail status`.
- `pre_launch_verify` runs a TCP probe for endpoint capabilities at launch. If the upstream service is slow or unreachable, `exec`/`shell`/`lock` is slow to start (mitigated by the existing 5s probe timeout and the `fatal: false` escape hatch).

**Reversibility**

Moderate. Restoring the polling loop is a single-method change in `Warden.supervise()`. Restoring the egress probe requires re-implementing `NetworkDrop.verify()` as a behavioral probe and re-evaluating the `commands/cap.py` `is_locked` check against the new protocol. The protocol change is additive — the old single-`check` shape can be re-derived by treating `verify() = check` everywhere.
