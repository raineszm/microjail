# Capability: lxd-event-monitor

## Purpose

The LXD event monitor subscribes to LXD lifecycle events for a single container via an `lxc monitor` subprocess and exposes them as a blocking iterator. The caller iterates with a `for` loop and gets one `LifecycleEvent` per iteration. The monitor does not interpret events or react to them; it only delivers them. Threading and queueing are out of scope; the caller can wrap the iterator in a thread + queue if parallel consumption is needed.

The subprocess is launched through the `CommandExecutor` protocol from `microjail.adapters.executor` (a standalone module, not defined inside `workshop.py`). `LxdMonitor.__init__` takes an optional `executor: CommandExecutor` parameter; the default is `LocalExecutor` from the same module. On `__iter__` the monitor calls `executor.popen(cmd, stdout=PIPE, text=True, bufsize=1)` to spawn `lxc monitor --project=<project> --type=lifecycle --format=json`. Tests substitute a fake executor that records the call and returns a fake `Popen` whose `stdout` is an iterable of preset lines.

## Requirements

### Requirement: LxdMonitor starts subprocess via CommandExecutor on iteration

When `__iter__` is first called, the LxdMonitor SHALL invoke the configured `CommandExecutor.popen` with the canonical command `["lxc", "monitor", "--project=<project>", "--type=lifecycle", "--format=json"]` and kwargs `stdout=PIPE, text=True, bufsize=1` to spawn the subprocess. The monitor MUST NOT call `subprocess.Popen` directly.

#### Scenario: One-shot iteration yields one matching event

- **GIVEN** an `LxdMonitor` is constructed for container `agent` in project `workshop`
- **AND** the executor's `popen` returns a `Popen` whose `stdout` yields the line `{"type":"lifecycle","timestamp":"2026-06-23T12:48:52.066853564-05:00","location":"none","project":"workshop","metadata":{"action":"instance-started","source":"/1.0/instances/agent","name":"agent","project":"workshop"}}` and then `""` (EOF)
- **WHEN** the caller iterates with `for event in monitor: ...` and then calls `monitor.close()`
- **THEN** the first iteration yields a `LifecycleEvent` with `event.metadata.action == "instance-started"`
- **AND** the loop terminates on the next call to `__next__` (subprocess EOF)

#### Scenario: `__iter__` invokes the configured `CommandExecutor.popen` with the canonical command

- **GIVEN** an `LxdMonitor` is constructed with a fake `CommandExecutor`
- **WHEN** `iter(monitor)` is called
- **THEN** the fake executor's `popen` method is invoked exactly once with the command `["lxc", "monitor", "--project=<project>", "--type=lifecycle", "--format=json"]`
- **AND** the kwargs include `stdout=PIPE`, `text=True`, `bufsize=1` for line-buffered reading
- **AND** `__iter__` does not call `subprocess.Popen` directly

### Requirement: LxdMonitor implements the Python iterator protocol

The `LxdMonitor` SHALL implement the Python iterator protocol: `__iter__` SHALL return `self` and SHALL spawn the `lxc monitor` subprocess on first invocation; `__next__` SHALL block until the next matching `LifecycleEvent` is available and return it, or raise `StopIteration` on subprocess stdout EOF. The monitor is single-use: if `__iter__` is called when a subprocess is already running, it SHALL raise `RuntimeError` rather than spawn a second subprocess.

#### Scenario: `__iter__` is single-use

- **GIVEN** an `LxdMonitor` is constructed and `iter(monitor)` has been called (subprocess is running)
- **WHEN** `iter(monitor)` is called again
- **THEN** `RuntimeError` is raised
- **AND** the existing subprocess is not replaced

### Requirement: LxdMonitor skips non-matching events during iteration

While iterating, the `LxdMonitor` SHALL drop events whose top-level `type` is not `"lifecycle"`, whose top-level `project` is not the configured LXD project, or whose `metadata.source` does not end with `/1.0/instances/<container_name>`. The container match SHALL be a full path-segment match: a source of `/1.0/instances/agent` matches container `agent`, but `/1.0/instances/evil-agent` SHALL NOT match container `agent`. The `LxdMonitor` SHALL yield at most one event per matching line.

#### Scenario: Non-matching events are skipped

- **GIVEN** an `LxdMonitor` is constructed for container `agent` in project `workshop`
- **AND** the executor's `popen` returns a `Popen` whose `stdout` yields four lines: a lifecycle event for `/1.0/instances/other`, a lifecycle event for project `other`, a `logging` event for `/1.0/instances/agent`, then a lifecycle event for `/1.0/instances/agent` in project `workshop`
- **WHEN** the caller iterates until `StopIteration`
- **THEN** exactly one `LifecycleEvent` is yielded
- **AND** its `metadata.source` is `/1.0/instances/agent`

### Requirement: LxdMonitor raises StopIteration on subprocess EOF

When the `lxc monitor` subprocess closes its stdout (normal exit, crash, or termination), the next call to `__next__` SHALL raise `StopIteration` so the surrounding `for` loop exits cleanly.

#### Scenario: StopIteration on EOF

- **GIVEN** an `LxdMonitor` is being iterated and the subprocess closes its stdout with no further events
- **WHEN** the caller calls `__next__`
- **THEN** `StopIteration` is raised

### Requirement: LxdMonitor terminates the subprocess on close

When `close()` is called, the `LxdMonitor` SHALL terminate the `lxc monitor` subprocess. After `close()` returns, the subprocess is no longer running. Calling `close()` more than once SHALL be a no-op.

#### Scenario: close() terminates the subprocess

- **GIVEN** an `LxdMonitor` is being iterated (subprocess is running)
- **WHEN** `close()` is called
- **THEN** the subprocess is terminated
- **AND** `close()` returns within the default timeout

#### Scenario: close() is idempotent

- **GIVEN** an `LxdMonitor` has been closed
- **WHEN** `close()` is called again
- **THEN** the subprocess is already terminated and no error is raised

### Requirement: LxdMonitor is a context manager that calls close() on exit

Where used as a context manager (`with LxdMonitor(...) as monitor: ...`), the `LxdMonitor` SHALL call `close()` from its `__exit__` method so the subprocess is terminated when the `with` block exits, including on exceptions. `__enter__` SHALL return `self`. The monitor MAY be used as either a context manager or a plain iterator — both styles are supported.

#### Scenario: Context manager terminates the subprocess on block exit

- **GIVEN** an `LxdMonitor` is constructed and iterated inside a `with` block
- **WHEN** the `with` block exits normally
- **THEN** the subprocess is terminated (the same observable effect as calling `close()` directly)

#### Scenario: Context manager terminates the subprocess on exception

- **GIVEN** an `LxdMonitor` is constructed and iterated inside a `with` block
- **AND** an exception is raised inside the block
- **WHEN** the `with` block exits
- **THEN** the subprocess is terminated before the exception propagates
- **THEN** the original exception is re-raised to the caller (not suppressed)
