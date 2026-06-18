## ADDED Requirements

### Requirement: Lifecycle event subscription
While a workload is running under Warden supervision, the LxdEventWatcher SHALL maintain a WebSocket subscription to the LXD `/1.0/events?type=lifecycle` stream, filtered to lifecycle events for the workload's container name and LXD project.

#### Scenario: Subscription starts on watcher start
- **GIVEN** a workload is running under Warden supervision
- **WHEN** the LxdEventWatcher is started
- **THEN** the watcher opens a WebSocket connection to `/1.0/events?type=lifecycle`
- **AND** the watcher client-side filters incoming events by `metadata.name == <container_name>` and `metadata.project == <lxd_project>`

#### Scenario: Matching event reaches the queue
- **GIVEN** the watcher is subscribed and the WebSocket is open
- **WHEN** an `instance-updated` event with `metadata.name == <container_name>` and `metadata.project == <lxd_project>` arrives on the WebSocket
- **THEN** the watcher enqueues a representation of the event for the Warden to consume

#### Scenario: Non-matching event is dropped
- **GIVEN** the watcher is subscribed and the WebSocket is open
- **WHEN** a lifecycle event whose `metadata.name` is a different container arrives
- **THEN** the watcher does not enqueue the event
- **AND** the WebSocket subscription remains open

### Requirement: Reconnect sentinel on every successful (re)connect
When the WebSocket connection is successfully established (initial connect and any reconnect after a disconnect), the LxdEventWatcher SHALL enqueue a `"reconnect"` sentinel so the Warden re-validates the lockdown against current LXD state.

#### Scenario: Initial connect emits sentinel
- **GIVEN** the watcher has not yet established a WebSocket connection
- **WHEN** the watcher successfully completes the initial WebSocket handshake
- **THEN** the watcher enqueues the literal string `"reconnect"` exactly once for that connection

#### Scenario: Reconnect after disconnect emits sentinel
- **GIVEN** the WebSocket was previously disconnected
- **WHEN** the watcher successfully completes a reconnect handshake
- **THEN** the watcher enqueues the literal string `"reconnect"` exactly once for that connection

#### Scenario: Failed handshake does not emit sentinel
- **GIVEN** the watcher is attempting to (re)connect
- **WHEN** the WebSocket handshake fails
- **THEN** the watcher does not enqueue the `"reconnect"` sentinel

### Requirement: Reconnect on disconnect with bounded backoff
If the WebSocket connection closes, the LxdEventWatcher SHALL attempt to reconnect with two backoff intervals: 0.3s before the first retry and 0.5s before the second retry. The total time from disconnect to escalation SHALL be under 1 second.

#### Scenario: First reconnect attempt
- **GIVEN** the WebSocket is disconnected
- **WHEN** the watcher initiates the first reconnect attempt
- **THEN** the watcher waits 0.3s before opening the new WebSocket connection

#### Scenario: Second reconnect attempt
- **GIVEN** the first reconnect attempt failed
- **WHEN** the watcher initiates the second reconnect attempt
- **THEN** the watcher waits 0.5s before opening the new WebSocket connection

### Requirement: Escalation after three failed reconnects
If three successive reconnect attempts fail, the LxdEventWatcher SHALL raise `LxdEnforcementLost` so the Warden can terminate the workload and surface the loss of enforcement.

#### Scenario: Three failures escalate
- **GIVEN** the WebSocket is disconnected
- **WHEN** the initial connect plus two reconnect attempts (with 0.3s and 0.5s backoffs) all fail
- **THEN** the watcher raises `LxdEnforcementLost`
- **AND** the watcher stops attempting further reconnects

#### Scenario: A successful reconnect resets the failure counter
- **GIVEN** one or more reconnect attempts have failed since the last successful connection
- **WHEN** a subsequent reconnect attempt succeeds
- **THEN** the failure counter resets to zero
- **AND** a new disconnect can be tolerated for up to three more failed reconnects before another escalation

### Requirement: Clean stop
When the LxdEventWatcher is stopped, the watcher SHALL close the WebSocket connection and terminate its reader thread within the current method call.

#### Scenario: Stop closes the WebSocket
- **GIVEN** the watcher is subscribed and the WebSocket is open
- **WHEN** the watcher is stopped
- **THEN** the watcher closes the WebSocket connection
- **AND** the reader thread terminates before `stop()` returns

#### Scenario: Stop is idempotent
- **GIVEN** the watcher has already been stopped
- **WHEN** the watcher is stopped a second time
- **THEN** the watcher does not raise

### Requirement: Container name and project passed to the watcher
The LxdEventWatcher SHALL receive the container name and LXD project as constructor parameters and SHALL use them for client-side event filtering and for the reconnect-sentinel scope.

#### Scenario: Construction records container and project
- **GIVEN** a container name and LXD project
- **WHEN** the LxdEventWatcher is constructed with both parameters
- **THEN** the watcher retains them for the lifetime of the instance
- **AND** the watcher uses them when filtering incoming lifecycle events
