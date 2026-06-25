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

- [x] 1.1 RED: test_warden_event_driven_passes_through_successful_exit
- [x] 1.2 GREEN: add `monitor_factory: Callable[[str, str], LxdMonitor] | None = None` kwarg to `Warden.__init__`; default to `LxdMonitor` (the class itself); rewrite `supervise()` to (1) call `self.check_policies()` as a baseline, (2) call `self.monitor_factory(self.microjail.container_name(), self.microjail.lxd_project())` to get the monitor, (3) call `iter(mon)` *inside* a `try:` block so `mon.close()` always runs on startup failure, (4) start a daemon `Thread` that runs `pump_events(mon, event_queue, stop)` (the pump iterates `mon`, pushes events, captures unexpected exceptions into a `MonitorError(exception)` wrapper, and pushes a `None` sentinel on normal EOF), (5) loop on `process.wait(timeout=self.interval)` + non-blocking `event_queue.get_nowait()`…
- [x] 1.3 REFACTOR: extract the pump body into a module-level `pump_events(mon, event_queue, stop)` function so the test for the thread lifecycle can target it directly; confirm `check_policies()` and `terminate_workload()` are unchanged; the `monitor_factory` kwarg is documented in the `Warden` docstring as the test injection point

## Slice 2: Warden re-runs check_policies on every LXD event

- **Test**: `test_warden_rechecks_policies_on_lxd_event` in `tests/unit/test_warden.py`
- **Status**: RED → GREEN already satisfied by Slice 1 implementation. The current `supervise()` drains the event queue and calls `check_policies()` after each `process.wait(timeout=interval)` timeout. No code change required; test locks in the behavior.

- [x] 2.1 RED: test_warden_rechecks_policies_on_lxd_event
- [x] 2.2 GREEN: no code change — Slice 1 implementation already drains the queue and re-runs `check_policies()` on each loop iteration
- [x] 2.3 REFACTOR: no refactor needed — current code is clean

## Slice 3: Warden re-runs check_policies on the fallback interval even when the monitor is quiet

- **Test**: `test_warden_rechecks_policies_on_fallback_interval_when_monitor_quiet` in `tests/unit/test_warden.py`
- **Status**: RED → GREEN already satisfied by Slice 1 implementation. The current `supervise()` calls `check_policies()` after every `process.wait(timeout=interval)` timeout regardless of whether events were delivered. No code change required; test locks in the behavior with an event-driven setup (FakeLxdMonitor).

- [x] 3.1 RED: test_warden_rechecks_policies_on_fallback_interval_when_monitor_quiet
- [x] 3.2 GREEN: no code change — Slice 1 implementation already runs `check_policies()` on the fallback interval
- [x] 3.3 REFACTOR: no refactor needed — current code is clean

## Slice 4: Baseline snapshot catches a pre-existing gate violation before the monitor opens

- **Test**: `test_warden_baseline_catches_pre_existing_gate_violation` in `tests/unit/test_warden.py`
- **Status**: RED → GREEN already satisfied by Slice 1 implementation. `supervise()` calls `self.check_policies()` at the start, before calling `self.monitor_factory(...)`. If the baseline check fails, `GatePolicyViolation` is raised and the monitor is never opened.

- [x] 4.1 RED: test_warden_baseline_catches_pre_existing_gate_violation
- [x] 4.2 GREEN: no code change — Slice 1 implementation already calls `check_policies()` before opening the monitor
- [x] 4.3 REFACTOR: no refactor needed — current code is clean

## Slice 5: Warden terminates the workload and raises GatePolicyViolation on a gate violation in the event path

- **Test**: `test_warden_terminates_on_gate_violation_in_event_path` in `tests/unit/test_warden.py`
- **Status**: RED → GREEN already satisfied by Slice 1 implementation. When the queue is drained and `check_policies()` runs after an event, a gate failure calls `terminate_workload()` and raises `GatePolicyViolation`. No code change required.

- [x] 5.1 RED: test_warden_terminates_on_gate_violation_in_event_path
- [x] 5.2 GREEN: no code change — Slice 1 implementation already handles gate violations in the event path
- [x] 5.3 REFACTOR: no refactor needed — current code is clean

## Slice 6: Warden escalates a gate violation to lxc stop --force when the workload does not exit on SIGTERM

- **Test**: `test_warden_escalates_gate_violation_in_event_path` in `tests/unit/test_warden.py`
- **Status**: RED → GREEN already satisfied by Slice 1 implementation. `terminate_workload()` is unchanged and still escalates to `lxc.stop_instance(..., force=True)` on SIGTERM timeout. No code change required.

- [x] 6.1 RED: test_warden_escalates_gate_violation_in_event_path
- [x] 6.2 GREEN: no code change — `terminate_workload()` is unchanged from the polling implementation
- [x] 6.3 REFACTOR: no refactor needed — current code is clean

## Slice 7: Warden warns on a non-fatal capability violation in the event path

- **Test**: `test_warden_warns_on_non_fatal_capability_violation_in_event_path` in `tests/unit/test_warden.py`
- **Status**: RED → GREEN already satisfied by Slice 1 implementation. When the queue is drained and `check_policies()` runs after an event, a non-fatal capability failure logs a warning to stderr and the workload is not terminated. No code change required.

- [x] 7.1 RED: test_warden_warns_on_non_fatal_capability_violation_in_event_path
- [x] 7.2 GREEN: no code change — Slice 1 implementation already handles non-fatal capability violations
- [x] 7.3 REFACTOR: no refactor needed — current code is clean

## Slice 8: Warden terminates the workload on a fatal capability violation in the event path

- **Test**: `test_warden_terminates_on_fatal_capability_violation_in_event_path` in `tests/unit/test_warden.py`
- **Status**: RED → GREEN already satisfied by Slice 1 implementation. When the queue is drained and `check_policies()` runs after an event, a fatal capability failure calls `terminate_workload()` and raises `CapabilityPolicyViolation`. No code change required.

- [x] 8.1 RED: test_warden_terminates_on_fatal_capability_violation_in_event_path
- [x] 8.2 GREEN: no code change — Slice 1 implementation already handles fatal capability violations
- [x] 8.3 REFACTOR: no refactor needed — current code is clean

## Slice 9: Warden treats monitor stream loss (StopIteration) as a gate policy violation

- **Test**: `test_warden_treats_monitor_stream_loss_as_gate_violation` in `tests/unit/test_warden.py`
- **Status**: RED → GREEN already satisfied by Slice 1 implementation. When the pump thread's `__next__` raises `StopIteration` (monitor closed), the pump pushes `None` into the queue. The supervision thread's queue drain detects `None`, calls `terminate_workload()`, and raises `GatePolicyViolation("LXD event monitor stream closed")`. No code change required.

- [x] 9.1 RED: test_warden_treats_monitor_stream_loss_as_gate_violation
- [x] 9.2 GREEN: no code change — Slice 1 implementation already treats stream loss as a gate violation
- [x] 9.3 REFACTOR: no refactor needed — current code is clean

## Slice 10: Default monitor factory constructs an LxdMonitor bound to the microjail's container and project

- **Test**: `test_warden_default_monitor_factory_is_lxd_monitor_class` in `tests/unit/test_warden.py`
- **Status**: RED → GREEN already satisfied by Slice 1 implementation. `Warden.__init__` sets `self.monitor_factory = LxdMonitor` when no factory is passed. The `LxdMonitor` class is the default and constructs an instance bound to the microjail's container and project when called. No code change required.

- [x] 10.1 RED: test_warden_default_monitor_factory_is_lxd_monitor_class
- [x] 10.2 GREEN: no code change — Slice 1 implementation already uses `LxdMonitor` as the default factory
- [x] 10.3 REFACTOR: no refactor needed — current code is clean
