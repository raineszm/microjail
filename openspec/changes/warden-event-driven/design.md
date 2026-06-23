## Context

The Warden is the runtime supervisor for a workload under an applied Lockdown. It currently polls each gate and capability every second, including behavioral probes (most notably `NetworkDrop`'s `bash -c ": >/dev/tcp/1.1.1.1/443"` egress probe). The polling model has three real problems: it is bash-dependent (false-positive gate violations on minimal images like alpine or distroless), it runs redundant probes that LXD already enforces at the kernel level, and it wastes CPU on stable workloads. The proposal established that under the threat model "LXD is the only thing with the power to enforce," the only way a gate can be violated during execution is via LXD configuration change — which the LXD lifecycle event stream sees directly. This design captures the implementation approach for switching the Warden to that event stream and refactoring the surrounding protocol.

## Goals / Non-Goals

**Goals:**

- Replace the per-second polling loop with a `lxc monitor --type=lifecycle --format=json` subprocess that streams lifecycle events.
- Eliminate the bash-dependency bug in `NetworkDrop.check()` by dropping the behavioral probe.
- Split the `Gate` and `Capability` protocols into a clear `check()` (config-state) and `verify()` (behavioral) pair, with each call site using the right one.
- Move capability checks out of the Warden's runtime loop and into a one-shot `pre_launch_verify()` step invoked by `lock`, `exec`, and `shell`.
- Force a Warden re-validation at watcher start via a `"reconnect"` sentinel, so the gates are re-checked even before the first real `instance-updated` event arrives.
- Treat every event-feed loss as a gate violation. The `lxc monitor` subprocess is the only supervision channel; if it exits, the workload is terminated immediately. No reconnect, no backoff, no budget.

**Non-Goals:**

- An asynchronous/await-based event loop. The Warden stays synchronous; the watcher uses a reader thread and a `queue.Queue`.
- Re-introducing behavioral probes for gates. Under the threat model, the probes are redundant and bug-prone.
- Runtime capability monitoring. Capabilities are launch-time only; the `fatal` flag is repurposed as a launch-time knob.
- New exit codes. `pre_launch_verify` reuses `GATE_APPLICATION_FAILURE` (68) and `CAPABILITY_APPLICATION_FAILURE` (66).
- A new pip dependency. The watcher uses the system `lxc` CLI; no new pip package is added.

## Decisions

### Decision 1 — `LxdEventWatcher` as a separate module

New file `src/microjail/adapters/lxd_events.py` with `class LxdEventWatcher` and `class LxdEnforcementLost(Exception)`. The watcher owns the `lxc monitor` subprocess, the `"reconnect"` sentinel emission (initial start only, per Decision 4), the event queue, and the escalation exception. There is no restart policy — subprocess exit raises `LxdEnforcementLost` immediately (per Decision 3).

The existing LXC adapter (`adapters/lxc.py`) is request/response (`subprocess.run(["lxc", ...])`). Mixing a long-lived subprocess lifecycle into that file would conflate two paradigms (one-shot CLI calls vs. a long-running event source). A separate module keeps the existing adapter focused and the watcher self-contained and individually testable.

**Alternatives considered:**

- Inline the subprocess in the `Warden` class. Rejected: the Warden would own subprocess management and escalation, making the supervision logic harder to test in isolation.
- Use the `pylxd` library. Rejected: a full LXD client library, not just events. The rest of the LXC integration is hand-rolled and the watcher should be too.

### Decision 2 — Synchronous queue + reader thread, not asyncio

`queue.Queue[str]` of event actions, written to by a reader thread inside `LxdEventWatcher`. The Warden's main thread uses `process.wait(timeout=0.1)` and `queue.get_nowait()` to multiplex. The Warden stays single-threaded.

Converting to asyncio would propagate to `MicroJail.popen`, `Workshop.popen`, `commands/supervision.py`, the `finally` block that does `process.terminate() / process.kill()`, every Typer command that calls `supervise_workload`, and the entire test suite. The benefit is sub-millisecond detection latency on a system where the worst-case impact of the 100ms poll is "the workload has 100ms more of unrestricted access during a stealthy host-side NIC re-add" — and even then the LXD kernel-level enforcement makes exfiltration impossible until the workload binds a socket to the new NIC. The cost is enormous and the win is theoretical.

**Alternatives considered:**

- Asyncio throughout. Rejected: large refactor for marginal latency improvement.
- `select.select` on the workload's pipe and a self-pipe woken by the watcher. Rejected: more complex than queue + thread; no benefit since the 100ms poll is already adequate.

### Decision 3 — Subprocess exit is an immediate gate violation; no reconnect

When the `lxc monitor` subprocess exits for any reason (LXD daemon stop, SIGHUP, the `lxc` binary crashing, a terminal readline error, the user running `pkill lxc`, etc.), the watcher raises `LxdEnforcementLost` immediately. There is no reconnect, no backoff, no retry, and no escalation budget — the loss of the event feed is itself a gate violation. The Warden catches `LxdEnforcementLost` in its main loop, calls `terminate_workload()`, and re-raises as `GatePolicyViolation` with the `RUNTIME_GATE_POLICY_VIOLATION` (84) exit code.

Under the threat model "LXD is the only thing that can enforce," a workload whose event feed has died is a workload we cannot supervise — and a workload we cannot supervise is a security regression. The previous design's 0.8s reconnect budget traded false-positive terminations (during transient LXD blips) for a small unsupervised window. This revision removes the trade: every event-feed loss is a violation. The cost is that any LXD daemon restart, `lxc` binary upgrade, or system-level OOM kill of the watcher subprocess terminates the workload. Users who run long-lived workloads accept that trade-off; users who need short-lived workloads under a stable LXD daemon see no behavior change.

**Alternatives considered:**

- Reconnect with bounded backoff (3 attempts at 0.3s, 0.5s). Rejected: introduces a window of unsupervised execution (up to 0.8s) where a malicious host could make an LXD configuration change that the Warden cannot detect. The cost (false-positive terminations on transient LXD blips) is real but small; the security cost (unsupervised execution window) is a direct violation of the threat model.
- Reconnect with generous backoff (1s, 2s, 4s, 7s budget). Rejected: same problem as above, with a longer unsupervised window.
- Loop forever, no escalation. Rejected: lets a workload run indefinitely without supervision after a multi-hour LXD outage.

### Decision 4 — `"reconnect"` sentinel on initial start, not on every restart

On the initial successful start of the `lxc monitor` subprocess, the watcher pushes the literal string `"reconnect"` onto the queue. The Warden treats it identically to any other event: re-snapshot `lxc_instance()` and re-run `check()` on every gate. The sentinel is emitted exactly once per watcher instance; because Decision 3 says the watcher never restarts the subprocess, the sentinel is never re-emitted.

The in-band string `"reconnect"` is preserved (rather than renamed to `"start"`) because the Warden's queue-drain logic uses string equality to detect the sentinel; renaming would require coordinated changes in two places for no behavioral benefit. The string is a historical artifact and a private protocol between the watcher and the Warden.

The sentinel forces a re-validation at watcher-startup time, even before the first real `instance-updated` event. Without it, a stable workload (no LXD configuration changes during its lifetime) would have its gates re-validated exactly once — at the moment the first real event arrived. With it, the Warden re-validates immediately on watcher start, closing the brief window between the lockdown apply and the watcher's first real event.

**Alternatives considered:**

- Re-snapshot only on real events, no sentinel. Rejected: a stable workload with no LXD configuration changes would never trigger a re-validation after the initial `pre_launch_verify`.
- Periodic re-snapshot on a timer. Rejected: re-introduces the polling the event-driven model is meant to remove.

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

### Decision 9 — `lxc monitor` subprocess, not a raw WebSocket

The watcher spawns `lxc monitor --type=lifecycle --format=json --quiet --project=<lxd_project> --force-local` as a subprocess and consumes its stdout line-by-line. The `lxc` CLI is the only system dependency; the watcher uses `subprocess.Popen` directly and does not import any third-party libraries. The subprocess constructor is injected (`popen: Callable[..., subprocess.Popen] = subprocess.Popen`) so tests can supply a stub without patching the global `subprocess` module.

Three properties drive this choice:

- **No cert handling.** The `lxc` CLI already authenticates to the LXD daemon (local socket or remote with the user's stored credentials). A raw WebSocket client would have to load the LXD client cert and key, manage the TLS handshake, and trust the daemon cert — work the `lxc` CLI has already done and continues to do correctly.
- **No socket management.** The LXD daemon's local Unix socket connection (or remote connection) is the `lxc` CLI's concern, not ours. A raw `/1.0/events` WebSocket client would have to discover and connect to the socket (or to a remote `wss://` endpoint) itself.
- **Consistent with the rest of the codebase.** Every other LXD interaction in microjail already shells out to the `lxc` CLI (`subprocess.run(["lxc", ...])`). Adding a subprocess to the mix stays within the established pattern. The `lxd_local_connect`-style "load cert, build SSL context, hand-roll WebSocket framing" path would be a new paradigm in this codebase.

The `lxc monitor` startup time is a few hundred milliseconds — well within the 0.3s/0.5s backoff budget. Startup latency is not a concern.

**Alternatives considered:**

- Raw WebSocket client via the `websockets` library, with cert handling in `adapters/lxc.py`. Rejected: introduces a transport-specific dependency (`websockets`) and a new auth/socket-management code path (`lxd_local_connect`) that the `lxc` CLI already handles. More code, more failure modes, no observable benefit.
- `pylxd`. Rejected: a full LXD client library, not just events; pulls in more than we need and would conflict with the hand-rolled `lxc` CLI approach used everywhere else.
- LXD REST API event stream over `lxc query`. Rejected: LXD does not expose a server-sent event stream on its REST API; events are only available over WebSocket. `lxc monitor` is the canonical CLI wrapper.

- **Any LXD daemon restart, `lxc` binary crash, or terminal readline error terminates the workload.** Unlike the previous design, which absorbed brief LXD blips via a 0.8s reconnect budget, this revision treats every event-feed loss as a gate violation. A 5–10s LXD daemon restart for a routine upgrade will terminate every running workload. → Mitigation: documented in ADR-0006 and the README; users who run long-lived workloads should run them in a context where the LXD daemon is stable, or accept the trade-off.
- **The window between `lxc monitor` startup and the first real event is short but non-zero.** A host-side `lxc config device add` during this window is not detected until either the next real `instance-updated` event or the next subprocess start (which, under this revision, never happens — the workload is already being terminated). → Mitigation: the `"reconnect"` sentinel forces a Warden re-validation immediately on initial subprocess start, closing most of this window. The remaining exposure is the time between subprocess start and the sentinel reaching the Warden (a few milliseconds).
- **Capability liveness is not monitored at runtime.** A Workshop-side operation that disconnects a tunnel after launch is not noticed. → Mitigation: `pre_launch_verify()` captures upstream liveness at the moment of launch; runtime capability liveness becomes an external concern (run `microjail status` to check).
- **No new exit code for "verify failure" vs "application failure."** A CI script cannot distinguish which step failed from the exit code alone. → Mitigation: the action is the same (don't run the workload); distinguishing the steps would add a code without changing the action.
- **`pre_launch_verify` runs a TCP probe for endpoint capabilities.** If the upstream service is slow or unreachable, `exec` / `shell` / `lock` is slow at launch. → Mitigation: the probe has its own timeout (existing `endpoint_reachable` has 5s); users can mark non-critical capabilities as `fatal: false` to convert the failure into a warning.
- **The `lxc` CLI must be on `$PATH`.** The watcher spawns `lxc monitor` directly; if the binary is missing, the subprocess fails to start, exits immediately, and the watcher escalates as a gate violation. → Mitigation: the rest of the LXC integration in microjail already requires `lxc` on `$PATH`; the watcher inherits the same prerequisite.
- **A leaked subprocess on `stop()`.** If `stop()` returns before the reader thread has reaped the subprocess, the OS may keep a zombie around until the parent process exits. → Mitigation: `stop()` calls `proc.terminate()`, waits for the reader thread to join, and the reader thread calls `proc.wait()` on its way out so the subprocess is reaped before `stop()` returns.

## Migration Plan

1. Land the new `adapters/lxd_events.py` first. New module, no behavior change.
2. Extend the `Gate` and `Capability` protocols with `verify()`. Implement `verify()` on all concrete gates and capabilities.
3. Refactor `NetworkDrop.check()` from the bash probe to a config check. Refactor `WorkshopEndpointCapability.check()` from the mixed check to the config check (tunnel state).
4. Add `MicroJail.pre_launch_verify()` and `PreLaunchVerifyResult`.
5. Wire `pre_launch_verify()` into `commands/lock.py`, `commands/exec.py`, `commands/shell.py`.
6. Rewrite `Warden.supervise()` around the event queue. Remove the capability loop. Add `LxdEnforcementLost` handling. The watcher's reader thread captures `LxdEnforcementLost` in `last_exception`; the Warden reads it on its next poll and escalates. There is no reconnect logic in the watcher — subprocess exit is the escalation trigger.
7. Update `commands/supervision.py` to handle `LxdEnforcementLost`.
8. Update unit, functional, and e2e tests.
9. Update `README.md` ("Warden polls policy every second" → "Warden is event-driven via `lxc monitor` lifecycle events").

Each step is independently revertible. The biggest refactor is step 6; the polling loop can be restored as a single-method change in `Warden.supervise()`. The protocol change is additive — the old single-`check` shape can be re-derived by treating `verify() = check` everywhere.

## Open Questions

None. All design decisions were resolved during the proposal phase. The implementation plan in the `tasks` artifact will surface any additional questions that arise during coding.
