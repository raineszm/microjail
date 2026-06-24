# Implementation Tasks

This change replaces the polling-based `Warden.supervise()` loop with an event-driven drain over an `LxdMonitor`. The interval is preserved as the fallback upper bound on tick latency and the timeout on `process.wait()`. A baseline `check_policies()` runs once before the monitor opens so a pre-existing violation is caught before the first event. Monitor stream loss is treated as a gate policy violation.

To prevent a hang when the workload exits while the supervision thread is blocked on `next(monitor)`, `supervise()` runs a background thread that pumps events from the `LxdMonitor` into a `queue.Queue`. The supervision thread loops on `process.wait(timeout=interval)` and a non-blocking queue drain. The `LxdMonitor` API itself is unchanged; threading and queueing live entirely inside `Warden`.

Vertical slices are organized by behavior: each slice adds one observable end-to-end behavior of the new `supervise()` loop. Within each slice, components are implemented with their own RED → GREEN → REFACTOR cycle (the inner loop). The `FakeLxdMonitor` test helper introduced in Slice 1 is a real blocking iterator (not a `Mock`) and is reused by every later slice; the `Mock(spec=MicroJail)` setup from the existing test file is reused as well.

## Slice 1: Tracer Bullet - Warden enters the event-driven loop, starts the pump thread, and passes through a successful exit

The minimum end-to-end path through the new shape: `Warden.supervise()` calls the baseline `check_policies()`, calls the `monitor_factory` to construct an `LxdMonitor`, calls `iter(monitor)` to start the subprocess, starts the pump thread, and returns the workload's exit code. This proves the loop runs without raising, the factory seam works, the pump thread start/join works, and the existing exit-code passthrough still works. Every later slice adds one observable behavior on top of this proven path.

- **Test**: `test_warden_event_driven_passes_through_successful_exit` in `tests/unit/test_warden.py`
- **Arrange**:
  - `mock_mj = Mock(spec=MicroJail)` with `mock_mj.lockdown = Mock()`, `mock_mj.lockdown.gates = []`, `mock_mj.lockdown.caps = []`. Empty lockdown makes the baseline `check_policies()` a no-op.
  - `mock_process = Mock(spec=subprocess.Popen)` with `mock_process.wait.return_value = 0`. The workload exits cleanly on the first `process.wait`.
  - A `FakeLxdMonitor` test helper is created in this slice. It is a real blocking iterator:
    - `__iter__` returns `self`; `__next__` blocks on a `threading.Event` until `deliver(event)` is called, then returns the queued event. If `close()` is called while `__next__` is blocked, it raises `StopIteration`.
    - `close()` sets the closed flag and wakes any pending `__next__` so the pump thread exits cleanly.
    - `deliver(event)` appends an event and wakes the pending `__next__`. Multiple `deliver` calls queue multiple events in order.
    - The fake does NOT use the context manager protocol — the real `LxdMonitor` does, but the pump-thread test cares about the iterator interface, not `with`. The fake's `close()` is what the Warden's `finally` calls.
  - `fake_monitor = FakeLxdMonitor()`; `monitor_factory = lambda c, p: fake_monitor` (the lambda accepts the `(container_name, lxd_project)` strings the Warden passes and ignores them; the fake doesn't need them). The Warden calls `self.monitor_factory(microjail.container_name(), microjail.lxd_project())` once at the start of `supervise()`.
  - `warden = Warden(mock_mj, mock_process, interval=0.01, monitor_factory=monitor_factory)`.
- **Act**:
  - `exit_code = warden.supervise()` (run on the test thread).
- **Assert**:
  - `exit_code == 0`.
  - `mock_process.wait.assert_called_once_with(timeout=0.01)`.
  - `fake_monitor.closed is True` (the supervision thread's `finally` called `close()`).
  - `monitor_factory` was called exactly once with two positional args (the `MicroJail`'s `container_name()` and `lxd_project()` strings).

- [ ] 1.1 RED: test_warden_event_driven_passes_through_successful_exit
- [ ] 1.2 GREEN: add `monitor_factory: Callable[[str, str], LxdMonitor] | None = None` kwarg to `Warden.__init__`; default to `LxdMonitor` (the class itself); rewrite `supervise()` to (1) call `self.check_policies()` as a baseline, (2) call `self.monitor_factory(self.microjail.container_name(), self.microjail.lxd_project())` to get the monitor, (3) call `iter(mon)` *inside* a `try:` block so `mon.close()` always runs on startup failure, (4) start a daemon `Thread` that runs `pump_events(mon, event_queue, stop)` (the pump iterates `mon`, pushes events, captures unexpected exceptions into a `MonitorError(exception)` wrapper, and pushes a `None` sentinel on normal EOF), (5) loop on `process.wait(timeout=self.interval)` + non-blocking `event_queue.get_nowait()` drain (events are coalesced — `check_policies()` runs once per loop iteration, not per event) + `self.check_policies()`, dispatching `None` to `GatePolicyViolation("LXD event monitor stream closed")` and `MonitorError` to `raise item.exception`, with a `finally` that sets `stop` and calls `mon.close()`; introduce `FakeLxdMonitor` at module level in `tests/unit/test_warden.py` with `deliver(event)`, `close()`, blocking `__next__`, and a `closed` flag
- [ ] 1.3 REFACTOR: extract the pump body into a module-level `pump_events(mon, event_queue, stop)` function so the test for the thread lifecycle can target it directly; confirm `check_policies()` and `terminate_workload()` are unchanged; the `monitor_factory` kwarg is documented in the `Warden` docstring as the test injection point

## Slice 2: [Pending] - Warden re-runs check_policies on every LXD event
<!-- Test details and tasks will be planned after Slice 1 is complete -->
- [ ] 2.1 RED: pending
- [ ] 2.2 GREEN: pending
- [ ] 2.3 REFACTOR: pending

## Slice 3: [Pending] - Warden re-runs check_policies on the fallback interval even when the monitor is quiet
<!-- Test details and tasks will be planned after Slice 2 is complete -->
- [ ] 3.1 RED: pending
- [ ] 3.2 GREEN: pending
- [ ] 3.3 REFACTOR: pending

## Slice 4: [Pending] - Baseline snapshot catches a pre-existing gate violation before the monitor opens
<!-- Test details and tasks will be planned after Slice 3 is complete -->
- [ ] 4.1 RED: pending
- [ ] 4.2 GREEN: pending
- [ ] 4.3 REFACTOR: pending

## Slice 5: [Pending] - Warden terminates the workload and raises GatePolicyViolation on a gate violation in the event path
<!-- Test details and tasks will be planned after Slice 4 is complete -->
- [ ] 5.1 RED: pending
- [ ] 5.2 GREEN: pending
- [ ] 5.3 REFACTOR: pending

## Slice 6: [Pending] - Warden escalates a gate violation to lxc stop --force when the workload does not exit on SIGTERM
<!-- Test details and tasks will be planned after Slice 5 is complete -->
- [ ] 6.1 RED: pending
- [ ] 6.2 GREEN: pending
- [ ] 6.3 REFACTOR: pending

## Slice 7: [Pending] - Warden warns on a non-fatal capability violation in the event path
<!-- Test details and tasks will be planned after Slice 6 is complete -->
- [ ] 7.1 RED: pending
- [ ] 7.2 GREEN: pending
- [ ] 7.3 REFACTOR: pending

## Slice 8: [Pending] - Warden terminates the workload on a fatal capability violation in the event path
<!-- Test details and tasks will be planned after Slice 7 is complete -->
- [ ] 8.1 RED: pending
- [ ] 8.2 GREEN: pending
- [ ] 8.3 REFACTOR: pending

## Slice 9: [Pending] - Warden treats monitor stream loss (StopIteration) as a gate policy violation
<!-- Test details and tasks will be planned after Slice 8 is complete -->
- [ ] 9.1 RED: pending
- [ ] 9.2 GREEN: pending
- [ ] 9.3 REFACTOR: pending

## Slice 10: [Pending] - Default monitor factory constructs an LxdMonitor bound to the microjail's container and project
<!-- Test details and tasks will be planned after Slice 9 is complete -->
- [ ] 10.1 RED: pending
- [ ] 10.2 GREEN: pending
- [ ] 10.3 REFACTOR: pending
