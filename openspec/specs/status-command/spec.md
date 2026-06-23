## Purpose

The `status-command` capability provides users with a diagnostic overview of their microjail project, including initialization state, workshop status, declared capabilities and gates, and live tunnel connections.

---

## Requirements

### Requirement: Status shows initialization state

When `microjail status` is called, the system SHALL report whether the project has been initialized (`.microjail/config.yaml` exists). If not initialized, the system SHALL display a message indicating the project is not initialized and suggesting `microjail init`.

#### Scenario: Status on uninitialized project reports not initialized
- **GIVEN** a project directory without `.microjail/config.yaml`
- **WHEN** `microjail status` is run
- **THEN** the output SHALL indicate the project is not initialized
- **AND** the output SHALL include the hint `Run 'microjail init' to create a microjail`

---

### Requirement: Status shows workshop info

When `microjail status` is called on an initialized project, the system SHALL display the workshop name and status (ready, pending, stopped, off, or unavailable).

#### Scenario: Status shows workshop name and status
- **GIVEN** an initialized project with workshop name "test-jail"
- **AND** the workshop daemon reports status "ready"
- **WHEN** `microjail status` is run
- **THEN** the output SHALL include the workshop name "test-jail"
- **AND** the output SHALL include the workshop status "ready"

#### Scenario: Status handles unreachable workshop daemon
- **GIVEN** an initialized project
- **AND** the workshop daemon is not running
- **WHEN** `microjail status` is run
- **THEN** the output SHALL show "unavailable" for the workshop status
- **AND** the system SHALL NOT crash

---

### Requirement: Status shows declared capabilities and gates

When `microjail status` is called, the system SHALL list all capabilities and gates declared in the lockdown policy, with their names and whether they are fatal.

#### Scenario: Status lists capabilities and gates
- **GIVEN** a lockdown with `WorkshopEndpointCapability("inference", host_endpoint="127.0.0.1:8080")`
- **AND** `NetworkDrop` and `ReadonlyConfig` gates
- **WHEN** `microjail status` is run
- **THEN** the output SHALL include the capability "inference"
- **AND** the output SHALL include gates "network-egress" and "readonly-config"

---

### Requirement: Status shows live tunnel connections

When `microjail status` is called, the system SHALL display current Workshop tunnel connections. The system SHALL gracefully handle cases where `workshop connections` fails.

#### Scenario: Status shows tunnel connections
- **GIVEN** an initialized project with an active tunnel connection
- **WHEN** `microjail status` is run
- **THEN** the output SHALL include the active connection details

#### Scenario: Status handles connections failure
- **GIVEN** an initialized project
- **AND** `workshop connections` fails (daemon unreachable)
- **WHEN** `microjail status` is run
- **THEN** the system SHALL NOT crash
- **AND** the output SHALL indicate connections are unavailable

---

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

---

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

---

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
