# Capability: warden-monitoring (delta)

This file modifies the existing `openspec/specs/warden-monitoring/spec.md` for the warden-event-driven change. The original spec described a polling-based Warden that re-checked gates and capabilities on a fixed interval. Under this change, the Warden is event-driven: it subscribes to LXD lifecycle events and re-validates gate configuration on each event. Capabilities are no longer monitored at runtime; their checks happen once at launch via `pre_launch_verify`.

## REMOVED Requirements

### Requirement: Warden monitoring loop checks active gates and capabilities
**Reason:** The Warden is no longer polling-based. It reacts to LXD lifecycle events. The per-second polling loop is removed; gate re-validation is event-driven. The capability check is removed from the runtime loop entirely (capabilities are checked once at launch via `pre_launch_verify`).

**Migration:** Behavior that depended on the polling loop is now triggered by LXD `instance-updated` events. Any external test or integration that asserted the polling interval should be updated to assert event-driven re-validation instead.

### Requirement: Workload process termination or warning on capability violation
**Reason:** The Warden no longer checks capabilities during execution. A capability that disappears mid-workload is not detected by the Warden; it is detected at launch time (via `pre_launch_verify`) and otherwise is a Workshop liveness concern, not a Microjail security concern.

**Migration:** The `fatal: bool` flag is repurposed as a launch-time knob. A `fatal` capability whose `verify()` fails at launch blocks the launch; a non-fatal failure is reported as a warning. Mid-workload capability liveness is not enforced.

## MODIFIED Requirements

### Requirement: Workload process termination on gate violation
The Warden MUST terminate the workload process immediately if any applied Gate's `check()` method returns `False` in response to an LXD lifecycle event for the workload's container, or if the LXD event subscription is lost (signaled by `LxdEnforcementLost`). The Warden MUST escalate the event-driven violation as a `GatePolicyViolation` and the `microjail` command MUST exit with code 84 (`RUNTIME_GATE_POLICY_VIOLATION`).

#### Scenario: Warden terminates workload on gate config drift
- **GIVEN** a workload is running under Warden supervision
- **WHEN** an LXD `instance-updated` lifecycle event causes any applied Gate's `check(microjail)` to return `False`
- **THEN** the Warden terminates the workload process
- **AND** the Warden escalates as `GatePolicyViolation`
- **AND** the `microjail exec` / `microjail shell` command exits with code 84

#### Scenario: Warden terminates workload on LxdEnforcementLost
- **GIVEN** a workload is running under Warden supervision
- **AND** the LXD event subscription is lost (the `LxdEventWatcher` has exhausted its 0.8s reconnect budget)
- **WHEN** the watcher raises `LxdEnforcementLost`
- **THEN** the Warden terminates the workload process
- **AND** the Warden escalates as `GatePolicyViolation`
- **AND** the `microjail exec` / `microjail shell` command exits with code 84

### Requirement: Warden handles normal workload exit
If the workload process exits normally without any policy violation, the Warden MUST stop the event subscription cleanly, preserve the applied Lockdown, and pass through the workload's exit code.

#### Scenario: Workload exits successfully
- **GIVEN** a workload is running under Warden supervision
- **WHEN** the workload process terminates with exit code 0
- **THEN** the Warden stops the `LxdEventWatcher` (closes the WebSocket, joins the reader thread)
- **AND** the `microjail exec` / `microjail shell` command exits with code 0
- **AND** the applied Lockdown is not released

#### Scenario: Workload exits with non-zero code
- **GIVEN** a workload is running under Warden supervision
- **WHEN** the workload process terminates with exit code 1
- **THEN** the Warden stops the `LxdEventWatcher`
- **AND** the `microjail exec` / `microjail shell` command exits with code 1
- **AND** the applied Lockdown is not released

## ADDED Requirements

### Requirement: Warden is event-driven via LXD lifecycle subscription
While a workload is running under Warden supervision, the Warden SHALL maintain a subscription to the LXD `/1.0/events?type=lifecycle` WebSocket stream for the workload's container and project, and SHALL re-validate every applied Gate's `check()` on every event for that container.

#### Scenario: Gate check runs on every matching event
- **GIVEN** a workload is running under Warden supervision
- **WHEN** an `instance-updated` event arrives for the workload's container
- **THEN** the Warden re-snapshots the LXD instance via `lxc_instance()`
- **AND** the Warden calls `check()` on every applied Gate
- **AND** the Warden terminates the workload on the first `check()` that returns `False`

#### Scenario: Non-matching events are ignored
- **GIVEN** a workload is running under Warden supervision
- **WHEN** a lifecycle event for a different container arrives
- **THEN** the Warden does not re-snapshot or re-check

#### Scenario: Warden re-validates on reconnect sentinel
- **GIVEN** the WebSocket subscription has just (re)connected
- **WHEN** the `LxdEventWatcher` enqueues the `"reconnect"` sentinel
- **THEN** the Warden treats the sentinel identically to any other event: re-snapshot and call `check()` on every Gate

### Requirement: Capabilities are not monitored at runtime
The Warden SHALL NOT call `check()` or `verify()` on any Capability during workload execution. Capability liveness is captured at launch time via `pre_launch_verify()`; runtime capability drift is not a Microjail security concern.

#### Scenario: Capability loop is absent from the Warden
- **GIVEN** a workload is running under Warden supervision with one or more Capabilities
- **WHEN** the Warden re-validates gates in response to an LXD event
- **THEN** the Warden iterates `lockdown.gates` only
- **AND** the Warden does not iterate `lockdown.caps`

### Requirement: LxdEnforcementLost escalates as a gate policy violation
If the `LxdEventWatcher` raises `LxdEnforcementLost` (LXD event subscription is lost after the 0.8s reconnect budget), the Warden SHALL terminate the workload and escalate the exception as a `GatePolicyViolation`. The escalation exit code is 84 (`RUNTIME_GATE_POLICY_VIOLATION`), matching the existing gate-violation exit code.

#### Scenario: LxdEnforcementLost terminates the workload
- **GIVEN** a workload is running under Warden supervision
- **WHEN** the `LxdEventWatcher` raises `LxdEnforcementLost` from its reconnect loop
- **THEN** the Warden calls `terminate_workload()` (terminate the process, escalate to `lxc stop --force` if the process does not exit within 2s)
- **AND** the Warden raises `GatePolicyViolation` so `supervise_workload` exits with code 84
