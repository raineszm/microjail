# Capability: lxd-event-monitor

## Purpose
The LXD event monitor subscribes to LXD lifecycle events for a single container via an `lxc monitor` subprocess and delivers matching events to in-process callers on a thread-safe queue. It is the foundation for an event-driven Warden; this capability does not interpret events or react to them, it only delivers them.

## ADDED Requirements

### Requirement: LxdMonitor subscribes to LXD lifecycle events for a single container
The `LxdMonitor` SHALL spawn an `lxc monitor` subprocess scoped to the configured LXD project, read its stdout line-by-line, and parse each non-empty line as a JSON object representing one LXD event.

#### Scenario: Monitor parses one lifecycle event from subprocess stdout
- **GIVEN** an `LxdMonitor` is constructed for container `agent` in project `workshop`
- **AND** the injected subprocess yields the line `{"type":"lifecycle","metadata":{"project":"workshop","action":"start","source":"/1.0/instances/agent"}}`
- **WHEN** `start()` is called
- **AND** the caller calls `events(timeout=1.0)`
- **THEN** the returned event equals the parsed JSON object above

### Requirement: LxdMonitor filters events to the configured container
While the monitor is running, the `LxdMonitor` SHALL drop events whose `metadata.source` does not identify the configured container before placing them on the internal queue.

#### Scenario: Monitor drops an event for a different container
- **GIVEN** an `LxdMonitor` is constructed for container `agent`
- **AND** the subprocess yields two lines: one whose `metadata.source` is `/1.0/instances/agent` and one whose `metadata.source` is `/1.0/instances/other`
- **WHEN** the caller reads events with `events(timeout=1.0)` until empty
- **THEN** the first call returns the `agent` event
- **AND** the second call returns `None` within the timeout

#### Scenario: Monitor drops a non-lifecycle event for the configured container
- **GIVEN** an `LxdMonitor` is constructed for container `agent`
- **AND** the subprocess yields a line whose top-level `type` is `logging` (not `lifecycle`) and whose `metadata.source` is `/1.0/instances/agent`
- **WHEN** the caller calls `events(timeout=0.1)`
- **THEN** the call returns `None`
- **AND** the monitor does not raise

### Requirement: LxdMonitor delivers events on a thread-safe queue
While the monitor is running, the `LxdMonitor` SHALL make parsed events available via `events(timeout)` from any thread, without requiring the caller to hold a lock.

#### Scenario: Caller retrieves an event from a different thread
- **GIVEN** an `LxdMonitor` is started and the subprocess has yielded one matching event
- **WHEN** a second thread calls `events(timeout=1.0)`
- **THEN** the call returns the matching event
- **AND** the call does not block past the timeout if no further events arrive

### Requirement: LxdMonitor exposes a timeout-bounded blocking events() method
The `LxdMonitor` SHALL provide an `events(timeout: float)` method that blocks up to `timeout` seconds for the next event, returns the event when one is available, and returns `None` if the timeout elapses with no event.

#### Scenario: events() returns None when the queue stays empty for the full timeout
- **GIVEN** an `LxdMonitor` is started
- **AND** no events have been received
- **WHEN** the caller calls `events(timeout=0.05)`
- **THEN** the call returns `None` within `0.1` seconds

#### Scenario: events() returns immediately when an event is already queued
- **GIVEN** an `LxdMonitor` is started
- **AND** at least one matching event is already on the queue
- **WHEN** the caller calls `events(timeout=5.0)`
- **THEN** the call returns the event without blocking on the timeout

### Requirement: LxdMonitor.start() spawns the monitor subprocess on demand
When `start()` is called, the `LxdMonitor` SHALL launch the configured subprocess exactly once. A second call to `start()` without an intervening `stop()` SHALL be a no-op.

#### Scenario: start() launches the subprocess
- **GIVEN** an `LxdMonitor` is constructed but not yet started
- **WHEN** `start()` is called
- **THEN** the injected launcher is invoked exactly once with the expected `lxc monitor` command and arguments

#### Scenario: A second start() does not relaunch the subprocess
- **GIVEN** an `LxdMonitor` has already been started
- **WHEN** `start()` is called again
- **THEN** the injected launcher is not invoked a second time

### Requirement: LxdMonitor.stop() terminates the subprocess and joins the reader thread
When `stop()` is called, the `LxdMonitor` SHALL terminate the subprocess and join the reader thread within the given `timeout` (default 5.0 seconds). After `stop()` returns, the monitor SHALL be in a stopped state and a subsequent `start()` SHALL relaunch the subprocess.

#### Scenario: stop() returns once the subprocess is terminated and the thread has joined
- **GIVEN** an `LxdMonitor` is started
- **WHEN** `stop(timeout=1.0)` is called
- **THEN** the subprocess is terminated
- **AND** the reader thread has exited
- **AND** the call returns within `1.0` second

#### Scenario: start() after stop() relaunches the subprocess
- **GIVEN** an `LxdMonitor` has been started and then stopped
- **WHEN** `start()` is called
- **THEN** the injected launcher is invoked a second time

### Requirement: LxdMonitor reports unrecoverable subscription loss via last_exception
If the `lxc monitor` subprocess exits with a non-zero status (or cannot be launched at all), the `LxdMonitor` SHALL populate the `last_exception` attribute with the underlying error and the reader thread SHALL exit. The monitor SHALL NOT silently retry the subscription on its own.

#### Scenario: last_exception is populated when the subprocess exits non-zero
- **GIVEN** an `LxdMonitor` is started with a fake subprocess that exits with status `1` and stderr `boom`
- **WHEN** the caller polls `last_exception` after the subprocess has terminated
- **THEN** `last_exception` is not `None`
- **AND** the underlying error references the non-zero exit and the stderr text

#### Scenario: events() continues to return None after subscription loss rather than raising
- **GIVEN** an `LxdMonitor` has lost its subscription and `last_exception` is set
- **WHEN** the caller invokes `events(timeout=0.05)`
- **THEN** the call returns `None` rather than raising

### Requirement: LxdMonitor drops malformed JSON lines without crashing
If the subprocess yields a line that is not valid JSON, the `LxdMonitor` SHALL drop the line, leave `last_exception` unchanged, and continue reading subsequent lines.

#### Scenario: A malformed line is dropped and parsing continues
- **GIVEN** an `LxdMonitor` is started
- **AND** the subprocess yields three lines in order: `not-json`, an empty line, then a valid event for the configured container
- **WHEN** the caller reads events with `events(timeout=0.5)` until empty
- **THEN** the valid event is returned
- **AND** `last_exception` remains `None`

### Requirement: LxdMonitor accepts an injected subprocess launcher for testability
Where a caller supplies a custom `MonitorLauncher` to the `LxdMonitor` constructor, the `LxdMonitor` SHALL use the supplied launcher instead of invoking `subprocess.Popen` directly.

#### Scenario: The injected launcher is used instead of subprocess.Popen
- **GIVEN** an `LxdMonitor` is constructed with a fake `MonitorLauncher`
- **WHEN** `start()` is called
- **THEN** the fake launcher is invoked with the expected command
- **AND** `subprocess.Popen` is not called with that command
