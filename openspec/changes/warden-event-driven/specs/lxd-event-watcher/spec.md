## ADDED Requirements

### Requirement: Lifecycle event subscription
While a workload is running under Warden supervision, the LxdEventWatcher SHALL run a `lxc monitor --type=lifecycle --format=json --quiet --project=<lxd_project> --force-local` subprocess and consume newline-delimited JSON events from its stdout. The watcher client-side filters the events to lifecycle events for the workload's container name.

#### Scenario: Subscription starts on watcher start
- **GIVEN** a workload is running under Warden supervision
- **WHEN** the LxdEventWatcher is started
- **THEN** the watcher spawns a `lxc monitor` subprocess with the required flags
- **AND** the watcher client-side filters the subprocess output by container name (matching `metadata.name` or, for events that omit it, the instance name parsed from `metadata.source`)

#### Scenario: Matching event reaches the queue
- **GIVEN** the watcher is running and the subprocess is alive
- **WHEN** a lifecycle event for the workload's container (matched by `metadata.name` or `metadata.source` derivation) and project is read from the subprocess stdout
- **THEN** the watcher enqueues the raw event line for the Warden to consume

#### Scenario: Non-matching event is dropped
- **GIVEN** the watcher is running and the subprocess is alive
- **WHEN** a lifecycle event for a different container is read from the subprocess stdout
- **THEN** the watcher does not enqueue the event
- **AND** the subprocess remains running

### Requirement: Reconnect sentinel on initial start
When the `lxc monitor` subprocess is successfully started for the first time, the LxdEventWatcher SHALL enqueue a `"reconnect"` sentinel so the Warden re-validates the lockdown against current LXD state. The sentinel is emitted exactly once per watcher instance, on initial start; because the watcher does not restart the subprocess, the sentinel is never emitted again.

#### Scenario: Initial start emits sentinel
- **GIVEN** the watcher has not yet started a `lxc monitor` subprocess
- **WHEN** the watcher successfully spawns the initial subprocess
- **THEN** the watcher enqueues the literal string `"reconnect"` exactly once

### Requirement: Subprocess exit is an immediate gate violation
If the `lxc monitor` subprocess exits (for any reason: LXD daemon stop, SIGHUP, the `lxc` binary crashing, a terminal readline error, etc.), the LxdEventWatcher SHALL raise `LxdEnforcementLost` so the Warden can terminate the workload and surface the loss of enforcement. The watcher SHALL NOT restart the subprocess; under the threat model "LXD is the only thing that can enforce," the loss of the event feed is itself a gate violation. The escalation is immediate — there is no reconnect budget, no backoff, and no retry.

#### Scenario: Subprocess exit escalates immediately
- **GIVEN** the watcher is running and the subprocess is alive
- **WHEN** the `lxc monitor` subprocess exits (any reason, any exit code)
- **THEN** the watcher raises `LxdEnforcementLost`
- **AND** the watcher does not attempt to restart the subprocess

### Requirement: Clean stop
When the LxdEventWatcher is stopped, the watcher SHALL terminate the `lxc monitor` subprocess and join its reader thread within the current method call. The stop path MUST be distinguished from a subprocess exit caused by an external failure: a stop-induced subprocess exit MUST NOT raise `LxdEnforcementLost`. `stop()` SHALL accept a timeout (default 5.0s) and SHALL call `terminate()` on the subprocess, escalating to `kill()` if the subprocess does not exit within the timeout.

#### Scenario: Stop terminates the subprocess
- **GIVEN** the watcher is running and the subprocess is alive
- **WHEN** the watcher is stopped
- **THEN** the watcher terminates the subprocess
- **AND** the reader thread terminates before `stop()` returns
- **AND** `LxdEnforcementLost` is NOT raised

#### Scenario: Stop escalates to kill on timeout
- **GIVEN** the watcher is running and the subprocess ignores SIGTERM
- **WHEN** the watcher is stopped with a 1.0s timeout
- **THEN** the watcher calls `kill()` on the subprocess
- **AND** the reader thread terminates before `stop()` returns

#### Scenario: Stop is idempotent
- **GIVEN** the watcher has already been stopped
- **WHEN** the watcher is stopped a second time
- **THEN** the watcher does not raise
