## ADDED Requirements

### Requirement: Warden monitoring loop checks active gates and capabilities
The Warden MUST periodically inspect all active Gates and Capabilities of a Lockdown applied to the Microjail instance at a configurable polling interval.

#### Scenario: Warden checks active gates and capabilities on interval
- **GIVEN** a workload is running under Warden supervision
- **WHEN** the polling interval passes
- **THEN** the Warden invokes `check` on all applied gates and capabilities of the microjail lockdown

### Requirement: Workload process termination on gate violation
The Warden MUST terminate the workload process immediately if any applied Gate fails its policy invariant check (its `check()` method returns `False`).

#### Scenario: Warden terminates workload when a Gate violation occurs
- **GIVEN** a workload is running under Warden supervision
- **WHEN** any applied Gate's `check()` returns `False` during the periodic poll
- **THEN** the Warden terminates the workload process immediately
- **AND** the Warden reports a Gate policy violation
- **AND** the run command exits with code 84

### Requirement: Workload process termination or warning on capability violation
The Warden MUST warn (log to stderr) when a Capability fails its check, unless the capability is configured as fatal, in which case the Warden MUST terminate the workload process immediately and exit with code 82.

#### Scenario: Warden warns on non-fatal capability violation
- **GIVEN** a workload is running under Warden supervision with default capability configuration
- **WHEN** an applied Capability's `check()` returns `False` during the periodic poll
- **THEN** the Warden logs a warning message to stderr
- **AND** the workload is not terminated

#### Scenario: Warden terminates workload on fatal capability violation
- **GIVEN** a workload is running under Warden supervision with a capability configured as fatal
- **WHEN** that Capability's `check()` returns `False` during the periodic poll
- **THEN** the Warden terminates the workload process immediately
- **AND** the Warden reports a Capability policy violation
- **AND** the run command exits with code 82

### Requirement: Warden handles normal workload exit
If the workload process exits normally without any policy violation, the Warden MUST stop monitoring, preserve the applied Lockdown, and pass through the workload's exit code.

#### Scenario: Workload exits successfully
- **GIVEN** a workload is running under Warden supervision
- **WHEN** the workload process terminates with exit code 0
- **THEN** the Warden stops monitoring
- **AND** the run command exits with code 0
- **AND** the applied Lockdown is not released

#### Scenario: Workload exits with non-zero code
- **GIVEN** a workload is running under Warden supervision
- **WHEN** the workload process terminates with exit code 1
- **THEN** the Warden stops monitoring
- **AND** the run command exits with code 1
- **AND** the applied Lockdown is not released
