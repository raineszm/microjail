## ADDED Requirements

### Requirement: Lockdown application reconciles Microjail-owned endpoint declarations

When Lockdown application starts Capability application, the system MUST remove Microjail-owned Workshop endpoint declarations that are not represented by current Endpoint Capability declarations before providing declared Endpoint capabilities.

#### Scenario: Lock removes stale Microjail-owned endpoint declaration
- **GIVEN** `.workshop/microjail/sdk.yaml` contains a plug named `old-api`
- **AND** `.microjail/config.yaml` does not declare an Endpoint Capability named `old-api`
- **WHEN** `microjail lock` applies the Lockdown
- **THEN** the `old-api` plug is removed from `.workshop/microjail/sdk.yaml`
- **AND** the same-named system slot is removed from `.workshop/<workshop-name>.yaml`

#### Scenario: Reconciliation preserves declared endpoint declaration
- **GIVEN** `.workshop/microjail/sdk.yaml` contains a plug named `inference`
- **AND** `.microjail/config.yaml` declares an Endpoint Capability named `inference`
- **WHEN** Lockdown application reconciles endpoint declarations
- **THEN** the `inference` plug is not removed as stale

#### Scenario: Reconciliation does not remove unrelated system slots
- **GIVEN** `.workshop/<workshop-name>.yaml` contains a system slot named `external`
- **AND** `.workshop/microjail/sdk.yaml` does not contain a plug named `external`
- **WHEN** Lockdown application reconciles endpoint declarations
- **THEN** the `external` system slot is not removed

### Requirement: Stale endpoint cleanup failure blocks Gate enforcement

If stale Microjail-owned endpoint declaration cleanup fails, then the system MUST report a Capability application failure and MUST NOT enforce Gates during that Lockdown application attempt.

#### Scenario: Lock stops before Gates when stale cleanup fails
- **GIVEN** a stale Microjail-owned endpoint declaration exists
- **AND** removing that stale declaration fails
- **WHEN** `microjail lock` applies the Lockdown
- **THEN** the command reports a Capability application failure
- **AND** no Gate enforcement is attempted

#### Scenario: Run does not start workload when stale cleanup fails
- **GIVEN** a stale Microjail-owned endpoint declaration exists
- **AND** removing that stale declaration fails
- **WHEN** `microjail run -- <command>` applies the Lockdown
- **THEN** Microjail reports a Capability application failure
- **AND** the workload command is not started

### Requirement: Stale endpoint cleanup is not rolled back

When stale Microjail-owned endpoint cleanup succeeds and a later Capability or Gate operation fails, the system MUST NOT restore the stale endpoint declaration during rollback.

#### Scenario: Failed run does not restore stale endpoint
- **GIVEN** Lockdown application removes a stale Microjail-owned endpoint declaration
- **AND** a later declared Capability fails before workload start during `microjail run`
- **WHEN** Microjail rolls back state applied during that failed run attempt
- **THEN** the stale endpoint declaration remains removed

## MODIFIED Requirements

### Requirement: Config type discriminator is `endpoint-proxy`

A YAML config entry with `type: endpoint-tunnel` MUST deserialize to a `WorkshopEndpointCapability` instance via the `dec_hook` in `microjail.py`. The `name`, `host_endpoint`, and optionally `container_endpoint` fields MUST be preserved.

#### Scenario: Config round-trip with both endpoints (port remap)
- **WHEN** the config YAML contains `- type: endpoint-tunnel\n  name: inference\n  host_endpoint: 127.0.0.1:8080\n  container_endpoint: 127.0.0.1:9090` under `lockdown.caps`
- **AND** `MicroJail.load(project_path)` is called
- **THEN** `microjail.lockdown.caps[0]` is a `WorkshopEndpointCapability` with `name="inference"`, `host_endpoint="127.0.0.1:8080"`, and `container_endpoint="127.0.0.1:9090"`

#### Scenario: Config round-trip without container endpoint
- **WHEN** the config YAML contains `- type: endpoint-tunnel\n  name: inference\n  host_endpoint: localhost:8080` under `lockdown.caps`
- **AND** `MicroJail.load(project_path)` is called
- **THEN** `microjail.lockdown.caps[0]` is a `WorkshopEndpointCapability` with `name="inference"`, `host_endpoint="localhost:8080"`, and `container_endpoint` is `None`
