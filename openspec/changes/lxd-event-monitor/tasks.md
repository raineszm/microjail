# Implementation Tasks

This change delivers a blocking iterator over LXD lifecycle events for a single container. Threading and queueing are out of scope; the future Warden integration is expected to wrap the iterator in a thread + queue if it needs parallel consumption.

Vertical slices are organized by behavior: each slice adds one observable end-to-end behavior of the `LxdMonitor` iterator. Within each slice, components are implemented with their own RED → GREEN → REFACTOR cycle (the inner loop).

## Slice 1: Tracer Bullet - LxdMonitor is a blocking iterator that yields one matching event

The minimum end-to-end path: construct an `LxdMonitor`, iterate over it, and observe that one matching lifecycle event comes through. This proves the whole iterator path works: `__iter__` starts the subprocess, `__next__` reads a line, parses it, filters it, and returns the event. Every later slice adds one observable behavior on top of this proven path.

- **Test**: `test_lxd_monitor_iteration_yields_matching_lifecycle_event` in `tests/unit/adapters/test_lxd_monitor.py`
- **Arrange**:
  - `LifecycleEvent` and `LifecycleMetadata` msgspec.Structs exist in `src/microjail/adapters/lxd_monitor.py` (already in place).
  - `parse_event(line)` and `matches(event, container_name, lxd_project)` exist (already in place).
  - `LxdMonitor` accepts `(container_name, lxd_project, executor)`. Default `executor` is `LocalExecutor` from `microjail.adapters.workshop`.
  - In the test, define a `FakePopen` whose `stdout` is an iterable yielding one lifecycle line then `""` (EOF). `terminate()` / `wait()` are no-ops. Define a `FakeExecutor` that records the call and returns the `FakePopen`.
  - Construct `monitor = LxdMonitor(container_name="agent", lxd_project="workshop", executor=FakeExecutor())`.
- **Act**:
  - Call `iter(monitor)` to start the subprocess.
  - Call `next(monitor)` to get the first event.
- **Assert**:
  - The first `next()` returns a `LifecycleEvent` with `metadata.action == "instance-started"`.

- [ ] 1.1 RED: test_lxd_monitor_iteration_yields_matching_lifecycle_event
- [ ] 1.2 GREEN: implement `LxdMonitor.__iter__`, `__next__`, and `close`; use the injected `CommandExecutor.popen` to spawn the subprocess with `stdout=PIPE, text=True, bufsize=1`
- [ ] 1.3 REFACTOR: no leaking internal state, the `FakePopen` / `FakeExecutor` helpers are clean and named for reuse in later slices

## Slice 2: [Pending] - Iterator skips non-matching events
<!-- Test details and tasks will be planned after Slice 1 is complete -->
- [ ] 2.1 RED: pending
- [ ] 2.2 GREEN: pending
- [ ] 2.3 REFACTOR: pending

## Slice 3: [Pending] - Iterator raises StopIteration on subprocess EOF
<!-- Test details and tasks will be planned after Slice 2 is complete -->
- [ ] 3.1 RED: pending
- [ ] 3.2 GREEN: pending
- [ ] 3.3 REFACTOR: pending

## Slice 4: [Pending] - close() terminates the subprocess and is idempotent
<!-- Test details and tasks will be planned after Slice 3 is complete -->
- [ ] 4.1 RED: pending
- [ ] 4.2 GREEN: pending
- [ ] 4.3 REFACTOR: pending

## Slice 5: [Pending] - LxdMonitor uses the injected CommandExecutor (no subprocess.Popen in __iter__ path)
<!-- Test details and tasks will be planned after Slice 4 is complete -->
- [ ] 5.1 RED: pending
- [ ] 5.2 GREEN: pending
- [ ] 5.3 REFACTOR: pending

## Slice 6: [Pending] - LxdMonitor is a context manager that calls close() on exit
Component-level (small): `__enter__` returns `self`; `__exit__` calls `self.close()`. Slice end-to-end: `with LxdMonitor(...) as monitor: for event in monitor: ...` terminates the subprocess when the block exits (normally or via exception).
<!-- Test details and tasks will be planned after Slice 5 is complete -->
- [ ] 6.1 RED: pending
- [ ] 6.2 GREEN: pending
- [ ] 6.3 REFACTOR: pending
