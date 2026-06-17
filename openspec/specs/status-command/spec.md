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
