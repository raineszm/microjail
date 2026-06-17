## MODIFIED Requirements

### Requirement: E2E tests cover Endpoint capability user journeys

The project MUST provide slow e2e coverage for declared Endpoint capability behavior through user configuration and CLI commands.

#### Scenario: Run reaches declared endpoint and blocks undeclared egress
- **WHEN** `.microjail/config.yaml` declares an Endpoint capability and `microjail run -- <command>` executes a workload that connects to that endpoint
- **THEN** the workload reached the declared endpoint and undeclared external network egress remains denied

#### Scenario: Run refuses workload start when Endpoint capability cannot be applied
- **WHEN** `.microjail/config.yaml` declares an Endpoint capability whose endpoint cannot be reached and `microjail run -- <command>` is invoked
- **THEN** Microjail returns a policy failure and the workload command does not start

#### Scenario: Unlock revokes declared Endpoint capability
- **WHEN** a declared Endpoint capability has been provided by a user-facing command
- **THEN** `microjail unlock` revokes that Endpoint capability separately from the test that proves the endpoint can be used during `run`

#### Scenario: CLI-added endpoint capability is usable during run
- **WHEN** `microjail cap add endpoint inference <host-endpoint>` adds an Endpoint Capability declaration
- **AND** `microjail run -- <command>` executes a workload that connects to that endpoint
- **THEN** the workload reaches the declared endpoint
- **AND** undeclared external network egress remains denied

### Requirement: Functional tests cover command-specific policy failure semantics

The project MUST provide functional tests proving `lock` and `run` handle capability and Gate application failures according to their distinct command semantics.

#### Scenario: Run blocks workload on capability application failure
- **WHEN** a required Capability cannot be applied during `microjail run`
- **THEN** the workload is not started and Gate enforcement for that run does not proceed after the blocking capability failure

#### Scenario: Lock continues to Gates after capability application failure
- **WHEN** a required Capability cannot be applied during `microjail lock`
- **THEN** Microjail still attempts implemented Gate enforcement and reports an incomplete non-zero result

#### Scenario: Run blocks workload on Gate application failure
- **WHEN** a Gate cannot be applied during `microjail run`
- **THEN** the workload is not started and the command returns a policy failure

#### Scenario: Lock stops before Gates on stale endpoint cleanup failure
- **WHEN** stale Microjail-owned Endpoint declaration cleanup fails during `microjail lock`
- **THEN** Microjail reports a Capability application failure
- **AND** Gate enforcement is not attempted

### Requirement: Functional tests cover documented config schema through CLI paths

The project MUST provide functional tests proving the documented YAML configuration shape is loaded correctly by user-facing commands.

#### Scenario: Endpoint capability config shape reaches command policy application
- **WHEN** `.microjail/config.yaml` contains a documented Endpoint capability entry with `type: endpoint-tunnel`, `name`, and `host_endpoint`
- **THEN** a CLI command load path constructs the Endpoint capability and includes it in policy application

#### Scenario: Default Gate config shape reaches command policy application
- **WHEN** `.microjail/config.yaml` contains documented Gate entries for `network-egress` and `readonly-config`
- **THEN** a CLI command load path constructs those Gates and includes them in policy application

#### Scenario: Duplicate Capability names are rejected before policy application
- **WHEN** `.microjail/config.yaml` contains two Capability entries with the same `name`
- **THEN** a CLI command load path reports a config validation error before applying policy

#### Scenario: Invalid Endpoint syntax is rejected before policy application
- **WHEN** `.microjail/config.yaml` contains an Endpoint capability entry whose endpoint fields are not valid simple `HOST:PORT` values
- **THEN** a CLI command load path reports a config validation error before applying policy

## ADDED Requirements

### Requirement: Functional tests cover Endpoint Capability CLI commands

The project MUST provide functional command tests for `microjail cap add endpoint` and `microjail cap remove endpoint` behavior that does not require real Workshop/LXD execution.

#### Scenario: Cap add endpoint writes config
- **GIVEN** a configured Microjail project whose Workshop state permits declaration editing
- **WHEN** `microjail cap add endpoint inference localhost:8080` is run through the command layer
- **THEN** `.microjail/config.yaml` contains the Endpoint Capability declaration

#### Scenario: Cap add endpoint replace requires flag
- **GIVEN** `.microjail/config.yaml` already declares Endpoint Capability `inference`
- **WHEN** `microjail cap add endpoint inference localhost:9090` is run through the command layer
- **THEN** the command fails and leaves the config unchanged

#### Scenario: Cap remove endpoint writes config
- **GIVEN** `.microjail/config.yaml` declares Endpoint Capability `inference`
- **WHEN** `microjail cap remove endpoint inference` is run through the command layer
- **THEN** `.microjail/config.yaml` no longer declares Endpoint Capability `inference`

#### Scenario: Cap apply refuses locked state
- **GIVEN** a configured Microjail project whose Workshop is ready
- **AND** a current Gate check returns true
- **WHEN** a `microjail cap` command is run through the command layer
- **THEN** the command fails before saving and tells the user to unlock before editing Capability declarations

#### Scenario: Cap apply updates stopped declarations only
- **GIVEN** a configured Microjail project whose Workshop is stopped or off
- **WHEN** `microjail cap add endpoint inference localhost:8080 --apply` is run through the command layer
- **THEN** the command updates Microjail and Workshop declaration files
- **AND** it does not start, refresh, or connect the Workshop
