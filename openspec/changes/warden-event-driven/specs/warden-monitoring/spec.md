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
The Warden MUST terminate the workload process immediately if any applied Gate's `check()` method returns `False` or raises an exception in response to an LXD lifecycle event for the workload's container, or if the LXD event subscription is lost (signaled by `LxdEnforcementLost`). The Warden MUST escalate the event-driven violation as a `GatePolicyViolation` and the `microjail` command MUST exit with code 84 (`RUNTIME_GATE_POLICY_VIOLATION`).

#### Scenario: Warden terminates workload on gate config drift
- **GIVEN** a workload is running under Warden supervision
- **WHEN** an LXD `instance-updated` lifecycle event causes any applied Gate's `check(microjail)` to return `False`
- **THEN** the Warden terminates the workload process
- **AND** the Warden escalates as `GatePolicyViolation`
- **AND** the `microjail exec` / `microjail shell` command exits with code 84

#### Scenario: Warden terminates workload on LxdEnforcementLost
- **GIVEN** a workload is running under Warden supervision
- **AND** the `lxc monitor` subprocess has exited (the LXD event feed is lost)
- **WHEN** the watcher raises `LxdEnforcementLost`
- **THEN** the Warden terminates the workload process
- **AND** the Warden escalates as `GatePolicyViolation`
- **AND** the `microjail exec` / `microjail shell` command exits with code 84

#### Scenario: Warden terminates workload when a gate check raises an exception
- **GIVEN** a workload is running under Warden supervision
- **WHEN** an LXD lifecycle event causes any applied Gate's `check(microjail)` to raise an exception (for example, an LXD query failure or a destroyed container)
- **THEN** the Warden terminates the workload process
- **AND** the Warden escalates as `GatePolicyViolation`
- **AND** the `microjail exec` / `microjail shell` command exits with code 84

### Requirement: Warden handles normal workload exit
If the workload process exits normally without any policy violation, the Warden MUST stop the event subscription cleanly, preserve the applied Lockdown, and pass through the workload's exit code.

#### Scenario: Workload exits successfully
- **GIVEN** a workload is running under Warden supervision
- **WHEN** the workload process terminates with exit code 0
- **THEN** the Warden stops the `LxdEventWatcher` (terminates the `lxc monitor` subprocess, joins the reader thread)
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
While a workload is running under Warden supervision, the Warden SHALL maintain a `lxc monitor --type=lifecycle --format=json --quiet --project=<lxd_project> --force-local` subprocess for the workload's container and project, and SHALL re-validate every applied Gate's `check()` on every event for that container.

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
- **GIVEN** the `LxdEventWatcher` has just been started (initial `lxc monitor` subprocess start)
- **WHEN** the `LxdEventWatcher` enqueues the `"reconnect"` sentinel
- **THEN** the Warden treats the sentinel identically to any other event: re-snapshot and call `check()` on every Gate

### Requirement: Capabilities are not monitored at runtime
The Warden SHALL NOT call `check()` or `verify()` on any Capability during workload execution. Capability liveness is captured at launch time via `pre_launch_verify()`; runtime capability drift is not a Microjail security concern.

#### Scenario: Capability loop is absent from the Warden
- **GIVEN** a workload is running under Warden supervision with one or more Capabilities
- **WHEN** the Warden re-validates gates in response to an LXD event
- **THEN** the Warden iterates `lockdown.gates` only
- **AND** the Warden does not iterate `lockdown.caps`

### Requirement: Termination failure does not mask the gate policy violation
The Warden's escalation path SHALL guarantee that the security-relevant `GatePolicyViolation` is surfaced to the caller even when the workload termination itself fails. A failure inside the termination path (for example, `lxc stop --force` failing because LXD is unreachable — the same condition that triggered the escalation) MUST NOT replace the `GatePolicyViolation` with a different exception. The `microjail` command MUST exit with code 84 (`RUNTIME_GATE_POLICY_VIOLATION`) whenever a gate violation or enforcement-loss condition has been detected, regardless of whether the termination succeeded.

#### Scenario: Escalation exits 84 even when lxc stop --force fails
- **GIVEN** the LXD daemon is unreachable
- **WHEN** the Warden decides to escalate (for example, because `LxdEnforcementLost` was raised, or a gate's `check()` raised because the LXD query itself failed)
- **AND** the worker's termination escalates to `lxc stop --force` which also fails
- **THEN** the `microjail` command exits with code 84
- **AND** no exception from the termination path replaces the `GatePolicyViolation`
