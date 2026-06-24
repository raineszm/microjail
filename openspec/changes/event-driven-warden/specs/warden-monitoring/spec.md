## MODIFIED Requirements

### Requirement: Warden monitoring loop checks active gates and capabilities
The Warden MUST invoke `check` on all applied gates and capabilities of the Lockdown applied to the Microjail instance after each iteration of the supervision loop. The loop waits for the workload process to exit or for the configured interval to elapse, whichever comes first; lifecycle events observed during a wait are coalesced into the next loop iteration rather than triggering immediate per-event checks. The interval caps the latency between a state change and a Warden-observed check.

#### Scenario: Warden checks active gates and capabilities in response to a lifecycle event
- **GIVEN** a workload is running under Warden supervision with an LXD event monitor open for the workload's container
- **WHEN** a lifecycle event for that container arrives during a supervision-loop wait
- **THEN** the Warden invokes `check` on all applied gates and capabilities of the microjail lockdown on the next loop iteration, not immediately on event arrival
- **AND** multiple events that arrive during a single wait are coalesced into a single check

#### Scenario: Warden re-checks on the configured interval as a fallback
- **GIVEN** a workload is running under Warden supervision with the fallback interval set to 1 second
- **WHEN** no lifecycle event for the workload's container has been delivered for 1 second
- **THEN** the Warden invokes `check` on all applied gates and capabilities of the microjail lockdown
- **AND** the fallback is independent of the event stream — it fires even when the monitor is quiet

### Requirement: Workload process termination on gate violation
The Warden MUST terminate the workload process immediately if any applied Gate fails its policy invariant check (its `check()` method returns `False`).

#### Scenario: Warden terminates workload when a Gate violation occurs
- **GIVEN** a workload is running under Warden supervision
- **WHEN** any applied Gate's `check()` returns `False` in response to a lifecycle event or a fallback poll
- **THEN** the Warden terminates the workload process immediately
- **AND** the Warden reports a Gate policy violation
- **AND** the run command exits with code 84

### Requirement: Workload process termination or warning on capability violation
The Warden MUST warn (log to stderr) when a Capability fails its check, unless the capability is configured as fatal, in which case the Warden MUST terminate the workload process immediately and exit with code 82.

#### Scenario: Warden warns on non-fatal capability violation
- **GIVEN** a workload is running under Warden supervision with default capability configuration
- **WHEN** an applied Capability's `check()` returns `False` in response to a lifecycle event or a fallback poll
- **THEN** the Warden logs a warning message to stderr
- **AND** the workload is not terminated

#### Scenario: Warden terminates workload on fatal capability violation
- **GIVEN** a workload is running under Warden supervision with a capability configured as fatal
- **WHEN** that Capability's `check()` returns `False` in response to a lifecycle event or a fallback poll
- **THEN** the Warden terminates the workload process immediately
- **AND** the Warden reports a Capability policy violation
- **AND** the run command exits with code 82

### Requirement: Warden handles normal workload exit
If the workload process exits normally without any policy violation, the Warden MUST stop monitoring (close the LXD event monitor), preserve the applied Lockdown, and pass through the workload's exit code.

#### Scenario: Workload exits successfully
- **GIVEN** a workload is running under Warden supervision
- **WHEN** the workload process terminates with exit code 0
- **THEN** the Warden closes the LXD event monitor
- **AND** the run command exits with code 0
- **AND** the applied Lockdown is not released

#### Scenario: Workload exits with non-zero code
- **GIVEN** a workload is running under Warden supervision
- **WHEN** the workload process terminates with exit code 1
- **THEN** the Warden closes the LXD event monitor
- **AND** the run command exits with code 1
- **AND** the applied Lockdown is not released

## ADDED Requirements

### Requirement: Warden establishes a baseline state snapshot before opening the LXD event monitor
The Warden MUST invoke `check` on all applied gates and capabilities once, before the LXD event monitor begins delivering events, so that any state already in violation at the moment supervision starts is caught before the monitor's first event. If the baseline check fails, the Warden MUST treat the result as a policy violation of the thing being checked (gate policy violation on the first failed gate; fatal capability policy violation if any fatal capability fails) and MUST NOT open the event monitor.

#### Scenario: Baseline snapshot catches a pre-existing gate violation
- **GIVEN** a workload is starting under Warden supervision
- **AND** an applied Gate is already unsatisfied at the moment supervision begins
- **WHEN** the Warden begins the supervision loop
- **THEN** the Warden terminates the workload before opening the LXD event monitor
- **AND** the Warden reports a Gate policy violation
- **AND** the run command exits with code 84

#### Scenario: Baseline snapshot passes and the monitor opens
- **GIVEN** a workload is starting under Warden supervision
- **AND** all applied gates and capabilities are satisfied at the moment supervision begins
- **WHEN** the Warden begins the supervision loop
- **THEN** the Warden opens the LXD event monitor
- **AND** the supervision loop enters the event-driven wait

### Requirement: Warden treats loss of the LXD event stream as a gate policy violation
The Warden MUST treat a closed LXD event monitor stream (subprocess EOF, `StopIteration` from the monitor iterator) as evidence that the Warden can no longer prove the Lockdown still holds. On stream loss, the Warden MUST terminate the workload, report a Gate policy violation, and exit with code 84.

#### Scenario: Monitor stream closes while the workload is still running
- **GIVEN** a workload is running under Warden supervision with the LXD event monitor open
- **WHEN** the LXD monitor subprocess closes its stdout (crash, termination, or normal exit) before the workload process exits
- **THEN** the Warden terminates the workload process
- **AND** the Warden reports a Gate policy violation
- **AND** the run command exits with code 84
