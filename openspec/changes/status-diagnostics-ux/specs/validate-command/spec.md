## ADDED Requirements

### Requirement: Validate checks schema conformance

When `microjail validate` is called, the system SHALL attempt to load and decode the config YAML through `MicroJail.load()`. If the file does not exist, the system SHALL report the project is not initialized. If the file exists but has a schema error (wrong field types, unknown struct tags, malformed YAML), the system SHALL report the parse error.

#### Scenario: Missing config reports not initialized

- **GIVEN** a project directory without `.microjail/config.yaml`
- **WHEN** `microjail validate` is run
- **THEN** the output SHALL indicate the project is not initialized
- **AND** the exit code SHALL be non-zero

#### Scenario: Invalid YAML reports schema error

- **GIVEN** a `.microjail/config.yaml` with a type error (e.g. a string where a number is expected)
- **WHEN** `microjail validate` is run
- **THEN** the output SHALL include an error about invalid config schema
- **AND** the exit code SHALL be non-zero

### Requirement: Validate detects duplicate capability names

When `microjail validate` is called and multiple capabilities share the same name, the system SHALL report each duplicate.

#### Scenario: Duplicate capability names reported

- **GIVEN** a lockdown with two capabilities both named "inference"
- **WHEN** `microjail validate` is run
- **THEN** the output SHALL include an error about duplicate name "inference"
- **AND** the exit code SHALL be non-zero

### Requirement: Validate detects invalid endpoint syntax

When `microjail validate` is called and an endpoint capability has an invalid endpoint address, the system SHALL report the error using the same `validate_endpoint_address` function used elsewhere in the codebase.

#### Scenario: Invalid endpoint address reported

- **GIVEN** a `WorkshopEndpointCapability` with endpoint address `invalid-url` (missing port)
- **WHEN** `microjail validate` is run
- **THEN** the output SHALL include an error about invalid endpoint syntax

### Requirement: Validate validates endpoint capability name format

When `microjail validate` is called, the system SHALL validate each endpoint capability's name using `validate_endpoint_name`.

#### Scenario: Invalid capability name reported

- **GIVEN** a `WorkshopEndpointCapability` with name `_bad_name` (starts with underscore)
- **WHEN** `microjail validate` is run
- **THEN** the output SHALL include an error about invalid endpoint name

### Requirement: Validate reports validation summary

When all validations pass, `microjail validate` SHALL report that the configuration is valid and exit with code 0.

#### Scenario: Valid configuration passes

- **GIVEN** a valid lockdown with no configuration errors
- **WHEN** `microjail validate` is run
- **THEN** the exit code SHALL be 0
- **AND** the output SHALL indicate the configuration is valid

### Requirement: Validate is read-only

When `microjail validate` is called, the system SHALL NOT modify any state — no config files are written, no Workshop state is changed, no capabilities are provided or revoked.

#### Scenario: Validate does not modify state

- **GIVEN** an initialized project
- **WHEN** `microjail validate` is run
- **THEN** no Workshop or MicroJail state SHALL be modified
