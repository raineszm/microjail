## ADDED Requirements

### Requirement: pre_launch_verify is invoked before any workload starts
When a workload-bearing command (`lock`, `exec`, or `shell`) has applied the Lockdown via `ensure_lockdown`, the system SHALL invoke `MicroJail.pre_launch_verify()` before any workload process is created, and SHALL display any returned warnings to stderr via the CLI `warning()` helper.

#### Scenario: lock calls pre_launch_verify after ensure
- **GIVEN** a `microjail lock` invocation on a project with an applied Lockdown
- **WHEN** the lockdown application completes via `ensure_lockdown`
- **THEN** `microjail.pre_launch_verify()` is called
- **AND** the returned `PreLaunchVerifyResult.non_fatal_capability_failures` is iterated
- **AND** each name is displayed to stderr via the CLI `warning()` helper

#### Scenario: exec calls pre_launch_verify before popen
- **GIVEN** a `microjail exec -- <command>` invocation
- **WHEN** the lockdown application completes via `ensure_lockdown`
- **THEN** `microjail.pre_launch_verify()` is called
- **AND** any returned warnings are displayed to stderr
- **AND** the workload `subprocess.Popen` is created only after `pre_launch_verify()` returns without raising

#### Scenario: shell calls pre_launch_verify before popen
- **GIVEN** a `microjail shell` invocation
- **WHEN** the lockdown application completes via `ensure_lockdown`
- **THEN** `microjail.pre_launch_verify()` is called
- **AND** any returned warnings are displayed to stderr
- **AND** the interactive shell `subprocess.Popen` is created only after `pre_launch_verify()` returns without raising

### Requirement: Gate verify failure raises GateError
If any Gate's `verify(microjail)` returns `False`, `pre_launch_verify()` SHALL raise `GateError` naming the failing gate, and SHALL NOT call `verify()` on the remaining gates.

#### Scenario: First gate verify failure raises GateError
- **GIVEN** a Lockdown with at least one Gate whose `verify(microjail)` returns `False`
- **WHEN** `pre_launch_verify()` is called
- **THEN** the method raises `GateError` with the failing gate's `name` attribute

#### Scenario: Subsequent gates are not checked after first failure
- **GIVEN** a Lockdown with three Gates, where the first gate's `verify(microjail)` returns `False` and the third gate's `verify(microjail)` would raise an exception if called
- **WHEN** `pre_launch_verify()` is called
- **THEN** the method raises `GateError` for the first gate
- **AND** the third gate's `verify()` is never called (no exception propagates from it)

### Requirement: Fatal capability verify failure raises CapabilityError
If any capability marked `fatal=True` has its `verify(microjail)` return `False`, `pre_launch_verify()` SHALL raise `CapabilityError` naming the first such fatal capability, and SHALL include the names of any non-fatal capabilities whose `verify()` failed earlier in the same pass in the `CapabilityError.non_fatal_failures` field. The method SHALL NOT call `verify()` on the remaining capabilities after that point.

#### Scenario: First fatal capability verify failure raises CapabilityError
- **GIVEN** a Lockdown with a capability marked `fatal=True` whose `verify(microjail)` returns `False`
- **WHEN** `pre_launch_verify()` is called
- **THEN** the method raises `CapabilityError` with the failing capability's `name` attribute

#### Scenario: Subsequent capabilities are not checked after first fatal failure
- **GIVEN** a Lockdown with three capabilities, where the first is marked `fatal=True` and its `verify(microjail)` returns `False`, and the third is also marked `fatal=True`
- **WHEN** `pre_launch_verify()` is called
- **THEN** the method raises `CapabilityError` for the first capability
- **AND** the third capability's `verify()` is never called

### Requirement: Non-fatal capability verify failures are collected
If a capability marked `fatal=False` has its `verify(microjail)` return `False`, `pre_launch_verify()` SHALL record the capability's `name` in the result and SHALL continue checking remaining capabilities.

#### Scenario: Single non-fatal failure is recorded
- **GIVEN** a Lockdown with one non-fatal capability whose `verify(microjail)` returns `False`
- **AND** all other gates and capabilities pass `verify()`
- **WHEN** `pre_launch_verify()` is called
- **THEN** the returned result's `non_fatal_capability_failures` contains exactly the failing capability's name
- **AND** the method does not raise

#### Scenario: Multiple non-fatal failures are all collected
- **GIVEN** a Lockdown with three non-fatal capabilities whose `verify(microjail)` all return `False`
- **WHEN** `pre_launch_verify()` is called
- **THEN** the returned result's `non_fatal_capability_failures` contains all three capability names in the order they were checked
- **AND** the method does not raise

### Requirement: CapabilityError carries the non-fatal failures collected before a fatal failure
`CapabilityError` SHALL expose a `non_fatal_failures` field (a tuple of capability names) that lists the non-fatal capabilities whose `verify()` failed earlier in the same `pre_launch_verify()` pass. The field is empty when no non-fatal failures preceded the fatal one. This allows the CLI to surface the earlier non-fatal failures as warnings alongside the fatal one.

#### Scenario: non_fatal_failures is empty when the fatal capability is the first failure
- **GIVEN** a Lockdown with a single fatal capability whose `verify(microjail)` returns `False`
- **AND** no other capabilities precede it
- **WHEN** `pre_launch_verify()` is called and the `CapabilityError` is caught
- **THEN** the exception's `non_fatal_failures` field is an empty tuple

#### Scenario: non_fatal_failures contains the names of all preceding non-fatal failures
- **GIVEN** a Lockdown with two non-fatal capabilities whose `verify(microjail)` returns `False`
- **AND** a later fatal capability whose `verify(microjail)` returns `False`
- **WHEN** `pre_launch_verify()` is called and the `CapabilityError` is caught
- **THEN** the exception's `non_fatal_failures` field contains both non-fatal capability names in the order they were checked

### Requirement: PreLaunchVerifyResult carries the warnings
`MicroJail.pre_launch_verify()` SHALL return a `PreLaunchVerifyResult` whose `non_fatal_capability_failures` field is a tuple of capability names. On full success, the tuple is empty.

#### Scenario: Result has empty tuple on full success
- **GIVEN** a Lockdown where every gate and every capability passes `verify()`
- **WHEN** `pre_launch_verify()` is called
- **THEN** the returned result is a `PreLaunchVerifyResult` with `non_fatal_capability_failures == ()`

### Requirement: lock exit codes for pre_launch_verify failures
When `pre_launch_verify()` raises during `microjail lock`, the `lock` command SHALL exit with the bitmask code corresponding to the failure: `GATE_APPLICATION_FAILURE` (68) for a `GateError`, `CAPABILITY_APPLICATION_FAILURE` (66) for a `CapabilityError`.

#### Scenario: Gate verify failure exits lock with code 68
- **GIVEN** a `microjail lock` invocation
- **WHEN** `pre_launch_verify()` raises `GateError`
- **THEN** `lock` exits with code 68

#### Scenario: Fatal capability verify failure exits lock with code 66
- **GIVEN** a `microjail lock` invocation
- **WHEN** `pre_launch_verify()` raises `CapabilityError`
- **THEN** `lock` exits with code 66

#### Scenario: Non-fatal warning does not change lock exit code
- **GIVEN** a `microjail lock` invocation
- **WHEN** `pre_launch_verify()` returns a result with one or more `non_fatal_capability_failures` entries
- **THEN** `lock` exits with code 0 after displaying the warnings
