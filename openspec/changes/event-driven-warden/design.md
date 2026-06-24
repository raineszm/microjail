## Context

The `Warden` in `src/microjail/warden.py` supervises a workload by polling every gate and capability on a fixed interval (default 1s) and terminating the workload on the first violation. The current loop is:

```python
def supervise(self) -> int:
    while True:
        try:
            return self.process.wait(timeout=self.interval)
        except subprocess.TimeoutExpired:
            self.check_policies()
```

Polling has two real costs. First, the host runs `gate.check()` and `cap.check()` on every tick for the entire workload lifetime, even when nothing has changed. Second, and more importantly, a device can be added and removed inside a single interval and the Warden never observes the violation — a real-time gap that poll-based monitoring cannot close.

The LXD daemon already broadcasts these changes as lifecycle events over `lxc monitor`. The recently-landed `LxdMonitor` (see `openspec/changes/archive/2026-06-23-lxd-event-monitor/` and `src/microjail/adapters/lxd_monitor.py`) is a blocking iterator over an `lxc monitor --type=lifecycle --format=json` subprocess, filtered to a single `(container_name, lxd_project)` pair. It is unit-testable without a real LXD daemon via an injected `CommandExecutor` and a fake `Popen`.

`DESIGN.md` (Runtime Enforcement, line 277) explicitly calls out: *"Polling is the correctness baseline. Event-driven monitoring may be added later as an optimization."* This change is that optimization. The `warden-monitoring` spec's polling wording is replaced by an event-driven wording with the interval re-scoped to a fallback upper bound.

## Goals / Non-Goals

**Goals:**
- Replace the polling-only `Warden.supervise()` loop with an event-driven drain over an `LxdMonitor` iterator.
- Multiplex event delivery with workload exit detection via a single background thread that pumps `LxdMonitor` events into a `queue.Queue`. Without this, `next(monitor)` would block on `readline()` while the workload has already exited, leaving the supervision thread hung until the next LXD event (or monitor EOF) — a real hang on quiet workloads. The `LxdMonitor` API itself is unchanged; threading and queueing are confined to the Warden.
- Reuse the existing `LxdMonitor` and `CommandExecutor` injection points — no new dependencies, no new subprocess plumbing.
- Keep the existing exit codes (82 for fatal capability violation, 84 for gate violation) and the existing `check_policies()` / `terminate_workload()` methods unchanged.
- Add a baseline state snapshot before the monitor opens, so a pre-existing violation is caught before the first event.
- Treat monitor stream loss as a gate policy violation, per the existing DESIGN.md line 298 principle: *"If Microjail cannot prove the Lockdown still holds, it assumes it does not hold."*
- Keep `Warden` unit-testable with a fake `LxdMonitor` returned from an injected `monitor_factory`. The fake must be a real blocking iterator (a `Mock` is not enough — see Decision 1).

**Non-Goals:**
- Reconnect / retry on monitor stream loss. The iterator ends with `StopIteration`; the Warden treats that as a fatal loss of observability.
- Reading non-lifecycle event types. The `LxdMonitor` already filters to lifecycle.
- Re-architecting the gate / capability protocols. `check()` is unchanged.
- Changing the CLI surface or the `commands.supervision.supervise_workload` signature.

## Decisions

### Decision 1: Pump LxdMonitor events into a queue from a background thread; the supervision loop multiplexes process.wait with the queue
- **Rationale**: A single `for event in monitor:` loop in the supervision thread is a hang on quiet workloads — `next(monitor)` blocks on `readline()` even after the workload process has exited, so the supervision thread would not notice the exit until the next LXD event (or monitor EOF). The fix is a small background thread that does nothing but call `next(mon)` and push the result into a `queue.Queue`. The supervision thread then loops on `process.wait(timeout=interval)` and a non-blocking queue drain. Workload exit is observed the instant `process.wait` returns; events are observed the instant the queue is non-empty; monitor EOF is signaled by a `None` sentinel in the queue. The `LxdMonitor` API itself is unchanged: it stays a blocking iterator, the thread is the wrapper.
- **The loop** (abbreviated; production code in Slice 1 follows this shape exactly):
  ```python
  def supervise(self) -> int:
      # 1. Baseline: catch pre-existing violations before opening the stream
      self.check_policies()

      # 2. Open the monitor inside the try block so mon.close() always runs.
      #    monitor_factory is Callable[[str, str], LxdMonitor]; default is the LxdMonitor class itself.
      mon = self.monitor_factory(self.microjail.container_name(), self.microjail.lxd_project())
      event_queue: queue.Queue[LifecycleEvent | MonitorError | None] = queue.Queue()
      stop = threading.Event()
      try:
          iter(mon)  # spawns the lxc monitor subprocess
          pump = threading.Thread(
              target=pump_events, args=(mon, event_queue, stop),
              daemon=True, name="warden-lxd-monitor-pump",
          )
          pump.start()
          # 3. Wait, drain, check, repeat
          while True:
              try:
                  return self.process.wait(timeout=self.interval)
              except subprocess.TimeoutExpired:
                  pass
              # Drain the queue. Events are coalesced; the check runs once
              # per loop iteration, not per event.
              while True:
                  try:
                      item = event_queue.get_nowait()
                  except queue.Empty:
                      break
                  if item is None:
                      # Monitor stream closed — can't prove Lockdown still holds
                      self.terminate_workload()
                      raise GatePolicyViolation("LXD event monitor stream closed")
                  if isinstance(item, MonitorError):
                      # Pump thread captured an unexpected exception; re-raise
                      raise item.exception
              self.check_policies()
      finally:
          stop.set()
          mon.close()


  @dataclass(frozen=True)
  class MonitorError:
      """Wrapper pushed by pump_events when it captures an unexpected exception."""
      exception: BaseException


  def pump_events(mon, event_queue, stop) -> None:
      """Iterate `mon`, push events to the queue. Push None on EOF.

      Unexpected exceptions are captured and pushed as MonitorError so the
      supervision thread can re-raise them on the main thread (where the
      exception can propagate to supervise_workload) instead of dying silently
      because the pump is daemon=True.
      """
      try:
          for event in mon:
              if stop.is_set():
                  return
              event_queue.put(event)
      except StopIteration:
          pass
      except BaseException as exc:
          event_queue.put(MonitorError(exception=exc))
          return
      event_queue.put(None)
  ```
  Three design points in this block:
  - **`iter(mon)` is inside the `try` block.** If `popen()` fails (lxc not on `$PATH`, daemon unreachable, subprocess crashes on startup), the `finally` still calls `mon.close()`. If `self._process` is None, `close()` is a no-op; if it's a dead subprocess, `close()` terminates it. No subprocess leak on startup failure.
  - **Events are coalesced, not per-event checked.** The queue drain discards events; `check_policies()` runs once per loop iteration. This matches the spec: checks fire after the interval, not per event. The interval caps the latency between a state change and a Warden-observed check.
  - **The pump captures unexpected exceptions and pushes a `MonitorError` wrapper.** A daemon pump that dies silently on exception leaves the supervision thread blocked on `process.wait(timeout=interval)` forever, with no signal that the monitor is gone. Capturing the exception and re-raising it on the supervision thread is the only way the user sees the underlying error. The supervision thread's `finally` still runs, so the monitor subprocess is terminated cleanly.
  The supervision thread's `finally` always runs (workload exit, violation, exception, pump failure), so the monitor subprocess is terminated on every code path. The pump thread is daemon, so even in a pathological case where the pump is wedged inside `next(mon)` despite `mon.close()`, the process can still exit.
- **Why a thread + queue, and not a single-threaded `selectors` approach?** `selectors.DefaultSelector` can wait on the monitor's stdout FD with a timeout, but the workload's exit is not a FD event — the process state has to be polled. A pure `selectors` loop would have to (a) reach inside `LxdMonitor` to grab the stdout FD, which is an internal attribute today, and (b) alternate `select()` with `process.poll()` calls. The thread+queue version adds a small amount of runtime overhead (one thread, one queue) in exchange for keeping `LxdMonitor` private and the loop linear. The `LxdMonitor` is a single-purpose building block; making the supervisor thread the orchestrator that introduces threading is the right separation of concerns.
- **Why does the pump thread not also call `check_policies`?** Because `check_policies` mutates workload state (calls `terminate_workload` on a gate violation) and reads the `MicroJail` lockdown; running it from a worker thread would require locking every `gate.check()` and `cap.check()` call. The supervision thread is the single owner of the workload and the lockdown; the pump thread is a pure event source. The pump *does* capture unexpected exceptions and surface them through the queue (see `MonitorError`) so the supervision thread can re-raise them on the main thread where they belong.
- **Why is the pump a daemon thread?** The supervision thread's `finally` block always calls `mon.close()` (which terminates the subprocess) and sets the stop signal, so the pump exits cleanly. A non-daemon thread would still exit cleanly, but daemon makes the lifecycle obvious to a reader.
- **Alternatives Considered**:
  - **Single-threaded `for event in monitor:` with `process.wait` calls between events**: rejected as the workload-exit-during-event-wait hang the user flagged.
  - **`selectors` on the monitor's stdout with `process.poll()` between `select` calls**: rejected as invasive (would need to expose the monitor's stdout FD on the public `LxdMonitor` interface) and no simpler than thread+queue.
  - **Asyncio with `asyncio.subprocess`**: rejected as out of scope. The rest of `microjail` is synchronous (`subprocess.Popen`, `lxc` client). Adding an asyncio loop inside `Warden.supervise` would be a much larger change with no upside.
  - **Use `process.wait(timeout=interval)` and ignore the monitor until the wait times out, then read everything that arrived in the meantime**: this is what the loop above does. The pump thread is just the "read in the meantime" half.

### Decision 2: Inject a `monitor_factory: Callable[[str, str], LxdMonitor]` at `__init__` time; default is the `LxdMonitor` class itself
- **Rationale**: `Warden.__init__` already takes `microjail` and `process`. The new `monitor_factory` parameter takes a two-argument callable that returns a fresh `LxdMonitor` given a `(container_name, lxd_project)` pair. The default is the `LxdMonitor` class itself — the simplest possible factory and the most explicit reference to the type. `supervise()` calls `self.monitor_factory(container_name, lxd_project)` once, passing the strings from the bound `MicroJail`. The kwarg name (`monitor_factory`) matches the attribute name (`self.monitor_factory`) for symmetry with `self.microjail`, `self.process`, `self.interval`.
- **Why does the factory take the strings, not no args?** The factory signature *is* the contract: "give me a container name and a project name, I'll give you a monitor." A no-arg factory would either (a) close over `microjail` (which couples the factory to a specific `MicroJail` instance — wrong for testing) or (b) be a class with no required args (which means the strings come from somewhere else — but the only reasonable source is `microjail`). Passing the strings explicitly is the standard constructor-call shape and is what a test fake accepts (and ignores) cleanly: `monitor_factory=lambda c, p: fake_monitor()`.
- **Why a factory and not an `LxdMonitor` instance?** Because the `LxdMonitor.__iter__` spawns the `lxc monitor` subprocess, and we want the subprocess lifecycle to live inside the `try`/`finally` in `supervise()`. A factory defers construction until supervision actually starts, so a `Warden` constructed but never used does not leave a subprocess behind. A factory is also the cleanest test seam: tests pass `monitor_factory=lambda c, p: fake_monitor()` and never have to construct a real `LxdMonitor` (or set up a `MicroJail.container_name()` / `MicroJail.lxd_project()` on their mocks).
- **Why is the default the class itself, not `None`?** Because "no monitor" is not a meaningful state for the Warden — the whole point of this change is to drain the monitor. A `None` default would either silently disable monitoring (a footgun) or require a runtime check in `supervise()` (clutter). The class as the default means the no-arg-injection case works end-to-end with zero ceremony: `Warden(microjail, process)` and `Warden(microjail, process, monitor_factory=LxdMonitor)` are equivalent.
- **Final shape**:
  ```python
  class Warden:
      def __init__(
          self,
          microjail: MicroJail,
          process: subprocess.Popen,
          interval: float = 1.0,
          monitor_factory: Callable[[str, str], LxdMonitor] | None = None,
      ) -> None:
          self.microjail = microjail
          self.process = process
          self.interval = interval
          self.monitor_factory: Callable[[str, str], LxdMonitor] = (
              monitor_factory if monitor_factory is not None else LxdMonitor
          )
  ```
  The class is the default; `supervise()` calls `self.monitor_factory(self.microjail.container_name(), self.microjail.lxd_project())` once at the start. Tests pass `monitor_factory=lambda c, p: fake_monitor()` (the lambda accepts and ignores the args, since the fake doesn't need them). The signature is the same shape as `LxdMonitor.__init__` itself, which is the right reference: a factory is "a thing that knows how to make a monitor given a container and a project," and the class is the canonical such thing.
- **Alternatives Considered**:
  - **Construct the `LxdMonitor` directly in `__init__`**: rejected — the subprocess would be spawned when the `Warden` is constructed, before `supervise()`. Hard to test, and it leaks the subprocess if `supervise()` is never called.
  - **Default to `None` and require callers to pass a factory explicitly**: rejected — there is no meaningful "no monitor" mode for the Warden, and a runtime check for `None` in `supervise()` is dead code in the production path.
  - **Make the entire `Warden` accept a `LxdMonitor` *and* a `CommandExecutor`**: rejected — the `LxdMonitor` already takes the `CommandExecutor`. Stacking another injection point on the `Warden` is redundant; the `LxdMonitor` is the layer that owns subprocess injection.
  - **No-arg factory (closure or partial)**: rejected — the bound-args shape makes the contract explicit ("here are the strings, give me a monitor") and is what the class's own constructor takes. A closure or partial would hide the strings inside the default and require tests to construct real `LxdMonitor` objects if they want to exercise the default path.

### Decision 3: Baseline snapshot is a one-shot `check_policies()` before the monitor opens
- **Rationale**: The `LxdMonitor` iterator only delivers *transitions* — the next event after `iter(monitor)` is whatever LXD emits next, not a snapshot of the current container state. If a gate or capability was already unsatisfied at the moment supervision starts, the iterator would not see the violation until the next event (or never, if the violating state is stable). The fix is one full `check_policies()` call before opening the monitor. This is exactly what the current polling Warden does on its first tick — we're keeping the "first-tick check" semantic, just front-loading it before the iterator starts.
- **What "baseline" means concretely**: a single call to `check_policies()` with the monitor not yet open. If it raises `GatePolicyViolation` or `CapabilityPolicyViolation`, the exception propagates to `supervise_workload`, which translates it to the existing exit code (84 or 82). The monitor is never opened in that case — the `with` block has not been entered.
- **Why not a richer baseline (e.g. `lxc query` for the full device set)?** Because `check_policies()` is exactly the existing baseline: it calls `gate.check()` and `cap.check()`, the same methods the polling Warden runs on every tick. A richer baseline would be a different contract; this change preserves the existing one.
- **Alternatives Considered**:
  - **Skip the baseline; trust the first event**: rejected — see above. A device attached and left attached before `iter(monitor)` would never trigger a check.
  - **Open the monitor first, run the baseline in a finally-style path**: rejected — the monitor would be alive while we're terminating for a baseline violation, leaking the subprocess into the termination path. Front-loading is simpler.
  - **Add a `baseline` method on `Warden` separately from `check_policies`**: rejected — there's nothing the baseline does that `check_policies` doesn't. Same method, called once.

### Decision 4: Monitor stream EOF → `GatePolicyViolation` (exit code 84)
- **Rationale**: The `LxdMonitor` iterator raises `StopIteration` when the `lxc monitor` subprocess closes its stdout (crash, termination, or normal exit). When that happens, the Warden can no longer observe state changes — it cannot prove the Lockdown still holds. Per DESIGN.md line 298, *"If Microjail cannot prove the Lockdown still holds, it assumes it does not hold."* The natural translation is: terminate the workload, report a gate policy violation, exit with 84. Gate violation is the right category because the design marks gates as fatal on loss; the existing capability-violation behavior is "warn by default, fatal if configured," which doesn't match "we lost observability entirely."
- **Why not a new exit code?** Because the proposal scopes this change to no new exit codes. The existing 84 is already the "we lost enforcement" code (its semantic in the polling world was "the gate that should hold doesn't hold"). Reusing it for "we can't see whether the gate still holds" is a clean extension of the same principle.
- **What the Warden does on EOF**:
  1. `terminate_workload()` — same SIGTERM-then-SIGKILL escalation as a gate violation.
  2. `raise GatePolicyViolation("LXD event monitor stream closed")` — translated by `supervise_workload` to exit 84, same as any other gate violation.
- **Alternatives Considered**:
  - **Add a new exit code (e.g. `RUNTIME_MONITOR_LOSS = POLICY_RESULT | RUNTIME_PHASE | 0x10`)**: rejected — the proposal says no new exit codes, and 84 is a reasonable fit. A future change can split out a more specific code if observability-loss turns out to be operationally distinct.
  - **Best-effort: warn and keep supervising with the fallback interval**: rejected — once the monitor is gone, the only enforcement left is the fallback poll, which is the same as the old behavior, and the user explicitly chose event-driven. Reverting silently to polling on EOF would be confusing; an explicit termination is clearer.
  - **Try to reconnect to the monitor**: rejected as scope creep. The `LxdMonitor` design (Decision 6 of its own design.md) explicitly leaves reconnect to the caller, and a future change can add a reconnecting `LxdMonitorSession` if that turns out to be what we want.

### Decision 5: `Warden.check_policies()` and `Warden.terminate_workload()` are unchanged
- **Rationale**: Both methods are correct as they are. `check_policies()` iterates gates, then capabilities, raises on the first gate failure, terminates on a fatal capability failure, warns on a non-fatal capability failure. `terminate_workload()` sends SIGTERM, waits 2s, escalates to `lxc stop --force` on the container if the process doesn't exit. These behaviors are exactly what the event-driven Warden needs on every event. Only the *trigger* changes.
- **Why not fold `check_policies()` into `supervise()`?** Because the baseline snapshot, the per-event check, and the test cases all want the same code path. A single `check_policies()` method keeps it that way.
- **Alternatives Considered**:
  - **Inline the check logic into the new event loop**: rejected — duplicates code between baseline and per-event, harder to test.

## Risks / Trade-offs

- **[Risk] `process.wait(timeout=interval)` blocks for the full interval when the monitor is quiet and the workload is running.** → *Mitigation*: this is intentional. A 1-second ceiling on tick latency is the documented contract. If a workload is heavy enough that 1s of slack is unacceptable, the caller can pass a smaller `interval` to `Warden.__init__` (e.g. 0.1s). The interval parameter is preserved.
- **[Risk] The baseline snapshot opens a tiny window for TOCTOU: a state change between the snapshot and the first event could be missed if it is reversed before the first event fires.** → *Mitigation*: that's the same risk any "check, then wait for events" approach has. The first matching event after the snapshot re-runs the full check, so a transient change followed by a stable reversion is caught by the next transition event. A permanent-but-stable change is caught by the baseline. The remaining gap is "change-and-revert inside the first event-less window" — which is also the only window where the polling Warden would have missed it.
- **[Risk] `terminate_workload()` on monitor EOF calls `lxc stop --force` from the existing path, while the monitor subprocess is also alive.** → *Mitigation*: the supervision thread's `finally` block calls `mon.close()` (which `terminate()`s the subprocess, waits 5s, then `kill()`s it) on every exit path — workload exit, violation, or exception. The two terminations are independent; the monitor subprocess and the workload process have no relationship that requires one to outlive the other. A test that calls `supervise()` and then asserts on a closed monitor subprocess will pass.
- **[Risk] The pump thread can outlive `supervise()` if `mon.close()` does not actually unblock `next(mon)`.** → *Mitigation*: `LxdMonitor.close()` calls `process.terminate()`, which closes the stdout pipe and causes `readline()` to return `''` → `StopIteration` → the pump's `for` loop exits → the pump puts the `None` sentinel and the thread ends. If `terminate()` fails to close the pipe (e.g. a wedged subprocess), `close()` escalates to `kill()` after a 5s wait, which closes the pipe. As a last line of defense, the pump thread is `daemon=True`, so even in a pathological case the thread does not keep the process alive past `supervise()`.
- **[Risk] A slow or deadlocked `gate.check()` or `cap.check()` on the supervision thread would still block the supervision loop — the pump thread is not affected, but the supervision thread's `check_policies()` would not return until the check unblocks.** → *Mitigation*: this is the same risk the polling Warden had. The pump thread continues to drain events while the supervision thread is blocked in `check_policies`; events that arrive during a slow check will be in the queue when the check returns and the next loop iteration drains them. Adding per-check timeouts is out of scope for this change.
- **[Risk] The default `LxdMonitor` constructed by the factory (the class itself) spawns an `lxc monitor` subprocess with no test-only `CommandExecutor` injection.** → *Mitigation*: production behavior is fine — the default `LxdMonitor` uses `LocalExecutor()`. Tests override `monitor_factory` and never call the default. The integration test path (if any) uses the same `LocalExecutor` as the rest of the codebase.
- **[Risk] The first event after `iter(monitor)` is the *next transition*, not the *current state*. The Warden might be tempted to assume the first event confirms the baseline.** → *Mitigation*: the spec and design call out explicitly that the baseline is the source of truth at moment zero; the first event is a delta from that baseline. The Warden does not use the first event to "confirm" the baseline — it just re-runs `check_policies()`.
- **[Trade-off] Lost-EOF behavior terminates the workload even if the LXD daemon hiccup is transient.** → This is by design: reconnection is out of scope, and silently reverting to polling would be confusing. A future change can add reconnect if the operational data shows the daemon drops the monitor stream often enough to matter.
- **[Trade-off] Event-driven monitoring ties the Warden to LXD.** The Warden now assumes the container is LXD-managed. → Already true in practice: the existing polling Warden calls `lxc.stop_instance(...)` on escalation, and `MicroJail.container_name()` returns an LXD container name. This change does not add a new LXD dependency; it deepens the existing one.

## Migration Plan

- **Code**: a single module (`src/microjail/warden.py`) is modified; the public class signature gains an optional `monitor_factory: Callable[[str, str], LxdMonitor] | None = None` kwarg. The default falls back to the `LxdMonitor` class itself, so the no-arg-injection case works end-to-end. No existing caller (`commands/supervision.py`) needs to change. The new internal surface is one background thread and one `queue.Queue` per `supervise()` call. `check_policies()` is also updated to wrap each `gate.check()` and `cap.check()` call in try/except so exceptions are treated as policy violations, per DESIGN.md line 298 (this is a pre-existing gap, not a regression, but the change touches `check_policies()` so it's the right place to fix it).
- **Tests**: `tests/unit/test_warden.py` is rewritten to use a fake `monitor_factory` that returns a `FakeLxdMonitor` (a real blocking iterator, not a `Mock`). The fake supports `__iter__` / `__next__` (blocking on a `threading.Event` until `deliver(event)` is called from the test thread), `close()` (unblocks any pending `__next__` with `StopIteration`), and a `lifecycle` flag pair. The existing test cases (successful exit, non-zero exit, gate violation, fatal capability violation, non-fatal capability warning, gate-violation escalation) all map 1:1 to the new event-driven model: instead of mocking `process.wait` to time out and trigger a poll, the test calls `fake_monitor.deliver(event)` to trigger `check_policies`. The pump-thread start/join and the monitor lifecycle (entered/exited/closed) are asserted on the fake.
- **Spec**: `openspec/specs/warden-monitoring/spec.md` is updated by the matching delta spec in this change. No other spec is affected.
- **Design**: `DESIGN.md` (Runtime Enforcement section, line 273) is updated to describe event-driven monitoring with the interval as a fallback. This is a one-paragraph edit to the existing "Polling is the correctness baseline. Event-driven monitoring may be added later as an optimization" sentence and the surrounding context.
- **No CLI change, no public API change, no schema change, no data migration, no flag.**
- **Rollback**: revert the commit. The polling behavior is fully restored; no callers depend on the event-driven shape.
