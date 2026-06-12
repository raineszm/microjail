## Why

Workloads currently run unsupervised within Microjail. The Warden (runtime supervisor) is required to continuously monitor policy invariants (gates and capabilities) under an applied Lockdown while a workload executes, terminating the workload immediately if any policy is violated to prevent unauthorized network egress or configuration tampering.

## What Changes

- Introduce the `Warden` class, a runtime supervisor for a workload running under an applied Lockdown.
- The Warden monitors policy invariants by periodically checking all active Gates and Capabilities (default: 1 second interval, configurable).
- If a Gate policy violation is detected, the Warden terminates the workload process immediately and exits with code 84.
- If a Capability policy violation is detected, the Warden warns by default (log to stderr) or terminates the workload process and exits with code 82 if the capability violation is configured as fatal in the configuration.
- Integrate `Warden` into the `microjail run` command so that workloads run under Warden supervision.
- Avoid releasing policy when the workload is terminated or exits, ensuring the Lockdown remains applied.

## Capabilities

### New Capabilities
- `warden-monitoring`: Periodic supervision of policy invariants (gates and capabilities) during workload execution and process termination on violation.

### Modified Capabilities
- `endpoint-capability`: Extended with a `fatal` configuration attribute to determine if policy check failures are warnings or fatal.
## Impact

- `src/microjail/warden.py`: A new module containing the `Warden` class and its supervision loop.
- `src/microjail/commands/run.py`: Updated to launch the workload asynchronously using `MicroJail.popen` and supervise it using the Warden.
- `tests/unit/test_warden.py`: Unit tests for Warden verification, polling intervals, and termination on policy violation.
- `tests/functional/commands/test_run.py`: Functional tests to verify CLI behavior when the Warden detects violations.
