## ADDED Requirements

### Requirement: Endpoint Capability declaration add command

The system SHALL provide `microjail cap add endpoint NAME HOST_ENDPOINT` to add an Endpoint Capability declaration to the current Lockdown without requiring manual YAML editing.

#### Scenario: Add endpoint capability declaration
- **GIVEN** a Microjail project whose Workshop state permits declaration editing
- **WHEN** the user runs `microjail cap add endpoint inference localhost:8080`
- **THEN** `.microjail/config.yaml` contains an Endpoint Capability declaration named `inference` with `host_endpoint="localhost:8080"`

#### Scenario: Add endpoint capability with container endpoint
- **GIVEN** a Microjail project whose Workshop state permits declaration editing
- **WHEN** the user runs `microjail cap add endpoint inference localhost:8080 --container-endpoint 10.0.0.1:9090`
- **THEN** `.microjail/config.yaml` contains an Endpoint Capability declaration named `inference` with `host_endpoint="localhost:8080"` and `container_endpoint="10.0.0.1:9090"`

#### Scenario: Add endpoint capability with fatal runtime behavior
- **GIVEN** a Microjail project whose Workshop state permits declaration editing
- **WHEN** the user runs `microjail cap add endpoint inference localhost:8080 --fatal`
- **THEN** `.microjail/config.yaml` contains an Endpoint Capability declaration named `inference` with `fatal=true`

### Requirement: Endpoint Capability declaration replacement

When an Endpoint Capability declaration already exists, the system SHALL require `--replace` before changing any declared Endpoint fields.

#### Scenario: Changed endpoint requires replace
- **GIVEN** `.microjail/config.yaml` declares an Endpoint Capability named `inference` with `host_endpoint="localhost:8080"`
- **WHEN** the user runs `microjail cap add endpoint inference localhost:9090`
- **THEN** the command fails before saving
- **AND** the existing Endpoint Capability declaration remains unchanged

#### Scenario: Replace changed endpoint
- **GIVEN** `.microjail/config.yaml` declares an Endpoint Capability named `inference` with `host_endpoint="localhost:8080"`
- **WHEN** the user runs `microjail cap add endpoint inference localhost:9090 --replace`
- **THEN** `.microjail/config.yaml` declares `inference` with `host_endpoint="localhost:9090"`

#### Scenario: Same-value add is idempotent
- **GIVEN** `.microjail/config.yaml` declares an Endpoint Capability named `inference` with `host_endpoint="localhost:8080"`
- **WHEN** the user runs `microjail cap add endpoint inference localhost:8080`
- **THEN** the command succeeds without changing the declaration

#### Scenario: Replace does not cross capability types
- **GIVEN** `.microjail/config.yaml` declares a non-Endpoint Capability named `inference`
- **WHEN** the user runs `microjail cap add endpoint inference localhost:8080 --replace`
- **THEN** the command fails before saving
- **AND** the non-Endpoint Capability declaration remains unchanged

### Requirement: Endpoint Capability declaration remove command

The system SHALL provide `microjail cap remove endpoint NAME` to remove an existing Endpoint Capability declaration from the current Lockdown.

#### Scenario: Remove endpoint capability declaration
- **GIVEN** `.microjail/config.yaml` declares an Endpoint Capability named `inference`
- **AND** the Workshop state permits declaration editing
- **WHEN** the user runs `microjail cap remove endpoint inference`
- **THEN** `.microjail/config.yaml` no longer contains the Endpoint Capability declaration named `inference`

#### Scenario: Remove missing endpoint fails
- **GIVEN** `.microjail/config.yaml` does not declare an Endpoint Capability named `inference`
- **WHEN** the user runs `microjail cap remove endpoint inference`
- **THEN** the command fails before saving

#### Scenario: Remove refuses wrong capability type
- **GIVEN** `.microjail/config.yaml` declares a non-Endpoint Capability named `inference`
- **WHEN** the user runs `microjail cap remove endpoint inference`
- **THEN** the command fails before saving
- **AND** the non-Endpoint Capability declaration remains unchanged

### Requirement: Endpoint Capability CLI validation

The system SHALL validate the entire current Lockdown before applying any `microjail cap` declaration edit and SHALL report all validation errors without mutating runtime state.

#### Scenario: Duplicate capability names are rejected
- **GIVEN** `.microjail/config.yaml` declares two Capabilities with the same name
- **WHEN** the user runs a `microjail cap` command
- **THEN** the command reports the duplicate Capability name as a config error
- **AND** the command does not save a modified config

#### Scenario: Invalid endpoint name is rejected
- **GIVEN** a Microjail project whose Workshop state permits declaration editing
- **WHEN** the user runs `microjail cap add endpoint 123_api localhost:8080`
- **THEN** the command reports that the Endpoint name is invalid
- **AND** the command does not save a modified config

#### Scenario: Invalid endpoint address is rejected
- **GIVEN** a Microjail project whose Workshop state permits declaration editing
- **WHEN** the user runs `microjail cap add endpoint inference http://localhost:8080`
- **THEN** the command reports that the Endpoint address is invalid
- **AND** the command does not save a modified config

### Requirement: Endpoint Capability apply option respects Workshop state

Where `--apply` is provided on a `microjail cap` command, the system SHALL update runtime or Workshop declarations only when the current Workshop state makes that safe.

#### Scenario: Apply fails when Workshop is not launched
- **GIVEN** a Microjail project whose Workshop is not launched
- **WHEN** the user runs `microjail cap add endpoint inference localhost:8080 --apply`
- **THEN** the command fails before saving
- **AND** the command tells the user to omit `--apply` for declaration-only setup or launch before applying

#### Scenario: Apply fails when Workshop is pending
- **GIVEN** a Microjail project whose Workshop status is `pending`
- **WHEN** the user runs `microjail cap add endpoint inference localhost:8080 --apply`
- **THEN** the command fails before saving

#### Scenario: Apply updates declarations only for stopped Workshop
- **GIVEN** a Microjail project whose Workshop status is `stopped` or `off`
- **WHEN** the user runs `microjail cap add endpoint inference localhost:8080 --apply`
- **THEN** `.microjail/config.yaml` contains the Endpoint Capability declaration
- **AND** the Microjail-owned Workshop endpoint declaration files are updated
- **AND** Workshop is not started, refreshed, or connected

#### Scenario: Apply uses Lockdown application for ready unlocked Workshop
- **GIVEN** a Microjail project whose Workshop status is `ready`
- **AND** no current Gate check returns true
- **WHEN** the user runs `microjail cap add endpoint inference localhost:8080 --apply`
- **THEN** `.microjail/config.yaml` contains the Endpoint Capability declaration
- **AND** the resulting Lockdown is applied through the same policy application behavior as `microjail lock`

#### Scenario: Apply refuses ready locked Workshop
- **GIVEN** a Microjail project whose Workshop status is `ready`
- **AND** at least one current Gate check returns true
- **WHEN** the user runs `microjail cap add endpoint inference localhost:8080 --apply`
- **THEN** the command fails before saving
- **AND** the command tells the user to unlock before editing Capability declarations

### Requirement: Endpoint Capability declaration-only edits warn when live state may lag

When a declaration-only `microjail cap` command changes config while a launched Workshop may retain older live or declaration state, the system SHALL warn that the updated Lockdown has not been applied.

#### Scenario: Declaration-only add warns for ready unlocked Workshop
- **GIVEN** a Microjail project whose Workshop status is `ready`
- **AND** no current Gate check returns true
- **WHEN** the user runs `microjail cap add endpoint inference localhost:8080`
- **THEN** the command saves the Endpoint Capability declaration
- **AND** the command warns that live Workshop state was not changed and `microjail lock` applies the updated Lockdown

#### Scenario: Declaration-only edit fails for unknown Workshop state
- **GIVEN** a Microjail project where Workshop state lookup fails
- **WHEN** the user runs `microjail cap add endpoint inference localhost:8080`
- **THEN** the command fails before saving

#### Scenario: Declaration-only edit fails for ready locked Workshop
- **GIVEN** a Microjail project whose Workshop status is `ready`
- **AND** at least one current Gate check returns true
- **WHEN** the user runs `microjail cap remove endpoint inference`
- **THEN** the command fails before saving
