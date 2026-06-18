## Context

The Warden is the runtime supervisor for a workload under an applied Lockdown. It currently polls each gate and capability every second, including behavioral probes (most notably `NetworkDrop`'s `bash -c ": >/dev/tcp/1.1.1.1/443"` egress probe). The polling model has three real problems: it is bash-dependent (false-positive gate violations on minimal images like alpine or distroless), it runs redundant probes that LXD already enforces at the kernel level, and it wastes CPU on stable workloads. The proposal established that under the threat model "LXD is the only thing with the power to enforce," the only way a gate can be violated during execution is via LXD configuration change — which the LXD lifecycle event stream sees directly. This design captures the implementation approach for switching the Warden to that event stream and refactoring the surrounding protocol.

## Goals / Non-Goals

**Goals:**

- Replace the per-second polling loop with a subscription to LXD's `/1.0/events?type=lifecycle` WebSocket stream.
- Eliminate the bash-dependency bug in `NetworkDrop.check()` by dropping the behavioral probe.
- Split the `Gate` and `Capability` protocols into a clear `check()` (config-state) and `verify()` (behavioral) pair, with each call site using the right one.
- Move capability checks out of the Warden's runtime loop and into a one-shot `pre_launch_verify()` step invoked by `lock`, `exec`, and `shell`.
- Self-heal on every WebSocket reconnect via a `"reconnect"` sentinel that triggers a re-snapshot and re-validation of every gate.
- Bound the disconnect window: three reconnect attempts at 0.3s, 0.5s backoff (0.8s total budget), then escalate as a `GatePolicyViolation`.

**Non-Goals:**

- An asynchronous/await-based event loop. The Warden stays synchronous; the watcher uses a reader thread and a `queue.Queue`.
- Re-introducing behavioral probes for gates. Under the threat model, the probes are redundant and bug-prone.
- Runtime capability monitoring. Capabilities are launch-time only; the `fatal` flag is repurposed as a launch-time knob.
- New exit codes. `pre_launch_verify` reuses `GATE_APPLICATION_FAILURE` (68) and `CAPABILITY_APPLICATION_FAILURE` (66).
- Hand-rolled WebSocket framing. The `websockets` library is added as a dependency.

## Decisions

### Decision 1 — `LxdEventWatcher` as a separate module

New file `src/microjail/adapters/lxd_events.py` with `class LxdEventWatcher` and `class LxdEnforcementLost(Exception)`. The watcher owns the WebSocket, the reconnect policy, the `"reconnect"` sentinel emission, the event queue, and the escalation exception.

The existing LXC adapter (`adapters/lxc.py`) is request/response (`subprocess.run(["lxc", ...])`). Mixing a long-lived WebSocket connection into that file would conflate two paradigms. A separate module keeps the existing adapter focused and the watcher self-contained and individually testable.

**Alternatives considered:**

- Inline the WebSocket in the `Warden` class. Rejected: the Warden would own transport details and reconnect policy, making the supervision logic harder to test in isolation.
- Use the `pylxd` library. Rejected: a full LXD client library, not just events. The rest of the LXC integration is hand-rolled and the watcher should be too.

### Decision 2 — Synchronous queue + reader thread, not asyncio

`queue.Queue[str]` of event actions, written to by a reader thread inside `LxdEventWatcher`. The Warden's main thread uses `process.wait(timeout=0.1)` and `queue.get_nowait()` to multiplex. The Warden stays single-threaded.

Converting to asyncio would propagate to `MicroJail.popen`, `Workshop.popen`, `commands/supervision.py`, the `finally` block that does `process.terminate() / process.kill()`, every Typer command that calls `supervise_workload`, and the entire test suite. The benefit is sub-millisecond detection latency on a system where the worst-case impact of the 100ms poll is "the workload has 100ms more of unrestricted access during a stealthy host-side NIC re-add" — and even then the LXD kernel-level enforcement makes exfiltration impossible until the workload binds a socket to the new NIC. The cost is enormous and the win is theoretical.

**Alternatives considered:**

- Asyncio throughout. Rejected: large refactor for marginal latency improvement.
- `select.select` on the workload's pipe and a self-pipe woken by the watcher. Rejected: more complex than queue + thread; no benefit since the 100ms poll is already adequate.

### Decision 3 — Reconnect policy: 3 attempts at 0.3s, 0.5s, then escalate

On disconnect (any `websockets.exceptions.ConnectionClosed` or similar), the watcher sleeps 0.3s, retries. On second failure, sleeps 0.5s, retries. On third failure, raises `LxdEnforcementLost`. The Warden catches this in its main loop, calls `terminate_workload()`, and re-raises as `GatePolicyViolation` with the `RUNTIME_GATE_POLICY_VIOLATION` (84) exit code.

Total time-to-escalation: 0.8s. Brief LXD blips (daemon restart, network hiccup) reconnect within seconds; the `"reconnect"` sentinel re-validates. Longer outages exceed the budget; the Warden escalates because under the threat model "LXD is the only thing that can enforce," running a workload we can't supervise is a security regression.

**Alternatives considered:**

- Loop forever, no escalation. Rejected: lets a workload run unsupervised during a multi-hour LXD outage.
- 3 attempts at 1s, 2s, 4s (7s budget). Rejected: too generous for the threat model.
- Single attempt. Rejected: false-positive terminations on transient blips.

### Decision 4 — `"reconnect"` sentinel for self-healing

On every successful (re)connect — initial and reconnects — the watcher pushes the literal string `"reconnect"` onto the queue. The Warden treats it identically to any other event: re-snapshot `lxc_instance()` and re-run `check()` on every gate.

WebSockets do not replay events missed during a disconnect. The sentinel makes the "next reconnect re-validates against current LXD state" guarantee explicit in code rather than implicit in the architecture. A long quiet period after a reconnect would otherwise leave drift undetected until the next real `instance-updated` event.

**Alternatives considered:**

- Re-snapshot only on real events, no sentinel. Rejected: a long quiet period after a reconnect would not trigger a re-validation.
- Sentinel on every connect AND on a periodic timer. Rejected: re-introduces the polling we just removed.

### Decision 5 — Protocol split: `check()` is config, `verify()` is behavioral

Every `Gate` and `Capability` exposes both `check(mj) -> bool` (config) and `verify(mj) -> bool` (behavioral). The Warden calls `check()` only. `pre_launch_verify()` calls `verify()` only.

The two checks have different semantic concerns. `check()` asks "does the system state match the gate's invariant?"; `verify()` asks "does the gate's behavioral aspect actually work?" Calling them both `check()` conflated the two and produced the bash-dependency bug. Splitting at the protocol level makes the concern explicit at every call site.

For the `Gate` protocol, `verify()` is required but a gate with no behavioral aspect (e.g. `NetworkDrop`, after the probe drop) implements it as `return True`. This keeps the protocol complete for future gates that may have a behavioral probe, while not requiring the current gates to do extra work.

For the `Capability` protocol, `verify()` is required. `WorkshopEndpointCapability` implements the TCP reachability probe; a future read-only mount capability (no behavioral aspect) would implement `verify() = return self.check(self)`.

**Alternatives considered:**

- Single `check()` method that dispatches internally. Rejected: hides the split, keeps the conflation, doesn't fix the protocol.
- Optional `verify()` via `getattr` at the call site. Rejected: hides the protocol from the type system; not idiomatic.

### Decision 6 — `pre_launch_verify()` returns a result dataclass, not None

```python
@dataclass(frozen=True)
class PreLaunchVerifyResult:
    non_fatal_capability_failures: tuple[str, ...] = ()

def pre_launch_verify(self) -> PreLaunchVerifyResult:
    ...
```

The runtime object should not depend on the CLI output module. Returning a result lets the caller (`lock`, `exec`, `shell`) iterate the warnings and call `warning()` from `commands/_output.py`. Tests can assert on the result without capturing stderr.

**Alternatives considered:**

- `-> None`, prints warnings internally. Rejected: couples runtime to CLI formatting; harder to test.
- Callback parameter `on_warning: Callable[[str], None]`. Rejected: more boilerplate at every call site for marginal benefit.

### Decision 7 — Reuse `GateError` and `CapabilityError`, not new types

`pre_launch_verify()` raises the existing `GateError` (from `lockdown.py`) on gate verify failure and the existing `CapabilityError` on fatal-capability verify failure. Exit codes reuse `GATE_APPLICATION_FAILURE` (68) and `CAPABILITY_APPLICATION_FAILURE` (66).

CONTEXT.md already defines "Gate application failure" as *"a failure to establish or verify a restriction..."* — so verify failures fit the existing terms. Reusing types and codes means a CI script handling "lockdown didn't establish" doesn't care whether the failure was at `ensure()` or `pre_launch_verify()`.

**Alternatives considered:**

- New types `GateVerifyError` and `CapabilityVerifyError`. Rejected: the difference between "application failure" and "verify failure" is a flow distinction, not a domain distinction.
- New bit (`LAUNCH_PHASE`) in the exit code. Rejected: bloats the bitmask; gives callers no new information.

### Decision 8 — `NetworkDrop` probe dropped entirely

`NetworkDrop.check()` becomes a config check (no devices of `type: nic` in `expanded_devices`). `NetworkDrop.verify()` returns `True`. The bash egress probe is removed from the codebase.

Under the threat model, the probe was redundant and bug-prone. LXD removes all NICs at apply time, making egress impossible at the kernel level. The probe tested one endpoint (1.1.1.1:443), required bash inside the container, and was subject to "tooling inside the container might be tampered with" caveats. The bash dependency caused false-positive violations on minimal images (alpine, distroless, scratch), which the `verify()`-as-no-op eliminates.

**Alternatives considered:**

- Improve the probe: `python3` based, multiple endpoints, faster timeout. Rejected: still redundant, still subject to the same caveats.
- Replace NIC removal with an LXD network ACL. Rejected: stronger but introduces a host-level side effect on `workshopbr0`; would require scoping work that's its own design exercise.

### Decision 9 — `websockets` library (synchronous client), not hand-rolled framing

Add `websockets` to `pyproject.toml`. `LxdEventWatcher` uses the synchronous `websockets.sync.client` API.

The WebSocket spec (RFC 6455) is fiddly. The `websockets` library is the de-facto Python implementation, well-tested, and actively maintained. Hand-rolling would be ~150 lines of framing code plus their own tests, and would be the only WebSocket implementation in the codebase (no second pair of eyes to catch bugs). The rest of the LXC adapter is hand-rolled `subprocess.run`, but those are request/response calls; WebSockets are a different paradigm and the library is the right tool for this concern.

**Alternatives considered:**

- Hand-rolled WebSocket framing. Rejected: significant complexity for a one-time concern.
- `pylxd`. Rejected: a full LXD client library, not just events; pulls in more than we need.

## Risks / Trade-offs

- **LXD daemon restarts during a workload's lifetime will trigger escalation.** A 5–10s daemon restart exceeds the 0.8s reconnect budget, so the Warden terminates the workload. → Mitigation: documented in ADR-0006 and the README; users who run long-lived workloads should run them in a context where the LXD daemon is stable, or accept the trade-off.
- **The 0.8s disconnect window is a blind window.** A host-side `lxc config device add` during the window is not detected until the next event or the next successful reconnect. → Mitigation: the `"reconnect"` sentinel re-validates on every successful reconnect, so any drift introduced during the window is caught at reconnect time.
- **Capability liveness is not monitored at runtime.** A Workshop-side operation that disconnects a tunnel after launch is not noticed. → Mitigation: `pre_launch_verify()` captures upstream liveness at the moment of launch; runtime capability liveness becomes an external concern (run `microjail status` to check).
- **No new exit code for "verify failure" vs "application failure."** A CI script cannot distinguish which step failed from the exit code alone. → Mitigation: the action is the same (don't run the workload); distinguishing the steps would add a code without changing the action.
- **`pre_launch_verify` runs a TCP probe for endpoint capabilities.** If the upstream service is slow or unreachable, `exec` / `shell` / `lock` is slow at launch. → Mitigation: the probe has its own timeout (existing `endpoint_reachable` has 5s); users can mark non-critical capabilities as `fatal: false` to convert the failure into a warning.

## Migration Plan

1. Land the new `adapters/lxd_events.py` first. New module, no behavior change.
2. Extend the `Gate` and `Capability` protocols with `verify()`. Implement `verify()` on all concrete gates and capabilities.
3. Refactor `NetworkDrop.check()` from the bash probe to a config check. Refactor `WorkshopEndpointCapability.check()` from the mixed check to the config check (tunnel state).
4. Add `MicroJail.pre_launch_verify()` and `PreLaunchVerifyResult`.
5. Wire `pre_launch_verify()` into `commands/lock.py`, `commands/exec.py`, `commands/shell.py`.
6. Rewrite `Warden.supervise()` around the event queue. Remove the capability loop. Add `LxdEnforcementLost` handling.
7. Update `commands/supervision.py` to handle `LxdEnforcementLost`.
8. Add `websockets` to `pyproject.toml`. Run `uv sync`.
9. Update unit, functional, and e2e tests.
10. Update `README.md` ("Warden polls policy every second" → "Warden is event-driven via LXD lifecycle events").

Each step is independently revertible. The biggest refactor is step 6; the polling loop can be restored as a single-method change in `Warden.supervise()`. The protocol change is additive — the old single-`check` shape can be re-derived by treating `verify() = check` everywhere.

## Open Questions

None. All design decisions were resolved during the proposal phase. The implementation plan in the `tasks` artifact will surface any additional questions that arise during coding.
