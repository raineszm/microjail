# Delta: status-command (modified capability)

## Purpose

Extend `microjail status` to show endpoint capability binding (host endpoint → container endpoint) and visually mark fatal capabilities. The existing requirements for initialization state, workshop info, capabilities list, gates list, and live tunnel connections are preserved.

## ADDED Requirements

### Requirement: Status shows endpoint binding for each endpoint capability

When `microjail status` is called on an initialized project, the system SHALL display, for each declared `WorkshopEndpointCapability`, the capability name, the declared `host_endpoint`, and the resolved container-side endpoint. The resolved container endpoint SHALL equal the declared `container_endpoint` if set, otherwise the declared `host_endpoint`. Capabilities with no `container_endpoint` declared SHALL show the host endpoint in both columns rather than abbreviating.

#### Scenario: Status shows host and container endpoint for each endpoint cap

- **GIVEN** a lockdown with `WorkshopEndpointCapability(name="inference", host_endpoint="127.0.0.1:8080", container_endpoint="127.0.0.1:9090")`
- **AND** `WorkshopEndpointCapability(name="local", host_endpoint="localhost:5000")` (no container endpoint)
- **WHEN** `microjail status` is run
- **THEN** the output contains the name "inference"
- **AND** the output contains the host endpoint "127.0.0.1:8080"
- **AND** the output contains the container endpoint "127.0.0.1:9090"
- **AND** the output contains the name "local"
- **AND** the output contains the endpoint "localhost:5000" (shown in both host and container columns, since no container endpoint is declared)

#### Scenario: Status renders empty capabilities list as "none"

- **GIVEN** an initialized project with no declared capabilities
- **WHEN** `microjail status` is run
- **THEN** the output indicates no capabilities are declared
- **AND** the existing workshop, gates, and connections output remains

### Requirement: Status marks fatal capabilities with a visual indicator

When `microjail status` is called and a declared `WorkshopEndpointCapability` has `fatal=True`, the system SHALL render that capability's row with a visible fatal indicator. Non-fatal capabilities SHALL NOT carry that indicator.

#### Scenario: Fatal capability carries the fatal indicator in the output

- **GIVEN** a lockdown with a fatal `WorkshopEndpointCapability` named `critical`
- **WHEN** `microjail status` is run
- **THEN** the output contains a fatal indicator character associated with the `critical` row
- **AND** the output contains the literal text `critical`

#### Scenario: Non-fatal capability does not carry the fatal indicator

- **GIVEN** a lockdown with a non-fatal `WorkshopEndpointCapability` named `inference`
- **AND** a fatal `WorkshopEndpointCapability` named `critical`
- **WHEN** `microjail status` is run
- **THEN** the row for `inference` does not carry the fatal indicator
- **AND** the row for `critical` does carry the fatal indicator

### Requirement: MicroJailStatus exposes endpoint capability details

The `MicroJailStatus` dataclass SHALL expose, for each declared `WorkshopEndpointCapability`, the capability's name, declared `host_endpoint`, resolved `container_endpoint`, and `fatal` flag. The information SHALL be carried in a new field `endpoint_capabilities: tuple[EndpointCapabilityInfo, ...]` with a default of `()` so existing positional construction of `MicroJailStatus` continues to work. `MicroJailStatus.endpoint_capabilities` SHALL contain one entry per declared `WorkshopEndpointCapability` in the loaded Lockdown, in declaration order.

#### Scenario: MicroJailStatus includes endpoint capability details for each cap

- **GIVEN** a lockdown with two `WorkshopEndpointCapability` declarations, one with `fatal=True` and one with `fatal=False`
- **WHEN** `MicroJail.status()` is called
- **THEN** `result.endpoint_capabilities` is a tuple of length 2
- **AND** each entry has `name`, `host_endpoint`, `container_endpoint`, and `fatal` populated
- **AND** the `fatal` values match the declarations
- **AND** the order matches declaration order

#### Scenario: MicroJailStatus default endpoint_capabilities is empty tuple

- **WHEN** `MicroJailStatus(workshop_name="x", workshop_status="y", capabilities=(), gates=(), connections=())` is constructed without the new field
- **THEN** the constructed object has `endpoint_capabilities == ()`

#### Scenario: EndpointCapabilityInfo resolves container_endpoint to host_endpoint when unset

- **WHEN** a `WorkshopEndpointCapability(name="local", host_endpoint="localhost:5000")` (no container endpoint) is in the Lockdown
- **AND** `MicroJail.status()` is called
- **THEN** the matching `EndpointCapabilityInfo` has `container_endpoint == "localhost:5000"`
