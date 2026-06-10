## MODIFIED Requirements

### Requirement: Endpoint is reachable after provide

After `WorkshopEndpointCapability.provide(microjail)` completes, the declared `host_endpoint` service MUST be reachable from inside the workshop container at the `container_endpoint` address. If `container_endpoint` is not set, it defaults to `host_endpoint`.

#### Scenario: Endpoint reachable inside container after provide

- **WHEN** `WorkshopEndpointCapability.provide(microjail)` is called with a running workshop
- **THEN** a TCP connection to `container_endpoint` (or `host_endpoint` if `container_endpoint` is unset) from inside the container succeeds

#### Scenario: Container endpoint differs from host endpoint (port remap)

- **WHEN** a `WorkshopEndpointCapability` is configured with `host_endpoint="127.0.0.1:8080"` and `container_endpoint="127.0.0.1:9090"`
- **AND** `provide(microjail)` completes successfully
- **THEN** a TCP connection to `127.0.0.1:9090` from inside the container succeeds
- **AND** the connection reaches the host service at `127.0.0.1:8080`

---

### Requirement: check reflects connection and reachability state

`WorkshopEndpointCapability.check(microjail)` MUST return `True` if and only if both conditions hold:
1. The Workshop tunnel connection (`<workshop>/microjail:<name>` → `<workshop>/system:<name>`) appears in `workshop connections` output.
2. The resolved endpoint (the `container_endpoint` field if set, otherwise `host_endpoint`) is reachable via TCP from inside the workshop container.

If either condition fails, `check()` MUST return `False`. `check()` MUST NOT raise.

#### Scenario: check returns False before provide

- **WHEN** `WorkshopEndpointCapability.check(microjail)` is called before `provide()` has been called
- **THEN** the return value is `False`

#### Scenario: check returns True after provide

- **WHEN** `WorkshopEndpointCapability.provide(microjail)` has completed successfully
- **AND** `WorkshopEndpointCapability.check(microjail)` is called
- **THEN** the return value is `True`

#### Scenario: check returns False after revoke

- **WHEN** `WorkshopEndpointCapability.revoke(microjail)` has completed
- **AND** `WorkshopEndpointCapability.check(microjail)` is called
- **THEN** the return value is `False`

#### Scenario: check returns False after workshop refresh

- **WHEN** `WorkshopEndpointCapability.provide(microjail)` has completed successfully
- **AND** `workshop refresh` is run externally
- **AND** `WorkshopEndpointCapability.check(microjail)` is called
- **THEN** the return value is `False`

This is expected: outgoing tunnel connections are not durable across refreshes. `ensure()` will call `provide()` again to reconnect before the workload starts.

#### Scenario: check returns False when workshop is not available

- **WHEN** `WorkshopEndpointCapability.check(microjail)` is called and the workshop container is not running
- **THEN** the return value is `False` and no exception is raised

---

### Requirement: provide writes plug to in-project SDK and slot to workshop definition

`WorkshopEndpointCapability.provide(microjail)` MUST write the plug declaration to `.workshop/microjail/sdk.yaml` (the in-project SDK owned by microjail) with `endpoint` set to the resolved container endpoint (`container_endpoint` if not `None`, otherwise `host_endpoint`). It MUST add the corresponding slot to the `system` SDK in the workshop definition at `.workshop/<workshop-name>.yaml` with `endpoint` set to `host_endpoint`. If `.workshop/microjail/sdk.yaml` does not exist it MUST be created. If `project-microjail` is not already listed in the workshop definition's `sdks`, it MUST be added.

#### Scenario: provide writes plug with container endpoint to in-project SDK file

- **WHEN** `WorkshopEndpointCapability.provide(microjail)` is called with `host_endpoint="127.0.0.1:8080"` and `container_endpoint="10.0.0.1:8080"`
- **THEN** `.workshop/microjail/sdk.yaml` contains a plug keyed `self.name` with `interface: tunnel` and `endpoint: "10.0.0.1:8080"` under the `plugs:` section

#### Scenario: provide writes plug with host endpoint when container endpoint is unset

- **WHEN** `WorkshopEndpointCapability.provide(microjail)` is called with `host_endpoint="localhost:8080"` and no `container_endpoint`
- **THEN** `.workshop/microjail/sdk.yaml` contains a plug keyed `self.name` with `interface: tunnel` and `endpoint: "localhost:8080"` under the `plugs:` section

#### Scenario: provide adds system slot with host endpoint to workshop definition

- **WHEN** `WorkshopEndpointCapability.provide(microjail)` is called with `host_endpoint="127.0.0.1:8080"`
- **THEN** `.workshop/<workshop-name>.yaml` contains a slot keyed `self.name` with `interface: tunnel` and `endpoint: "127.0.0.1:8080"` under the `system` SDK's `slots:` section

#### Scenario: provide adds project-microjail to sdks list when absent

- **WHEN** `WorkshopEndpointCapability.provide(microjail)` is called and `project-microjail` is not in the workshop definition's `sdks` list
- **THEN** `project-microjail` is added to the `sdks` list

#### Scenario: provide does not duplicate project-microjail entry

- **WHEN** `WorkshopEndpointCapability.provide(microjail)` is called and `project-microjail` is already in the workshop definition's `sdks` list
- **THEN** the `sdks` list contains exactly one `project-microjail` entry

---

### Requirement: Capability has a stable name

`WorkshopEndpointCapability.name` MUST equal the `name` string provided at construction. `WorkshopEndpointCapability.host_endpoint` MUST equal the `host_endpoint` string provided at construction. `WorkshopEndpointCapability.container_endpoint` MUST be the `container_endpoint` string if provided, otherwise `None`. The name is used as the Workshop plug/slot identifier and MUST be a valid Workshop identifier (letters, digits, hyphens; starts with a letter).

#### Scenario: Capability fields are preserved

- **WHEN** `WorkshopEndpointCapability(name="inference", host_endpoint="127.0.0.1:8080", container_endpoint="10.0.0.1:8080")` is instantiated
- **THEN** `cap.name == "inference"`
- **AND** `cap.host_endpoint == "127.0.0.1:8080"`
- **AND** `cap.container_endpoint == "10.0.0.1:8080"`

#### Scenario: container_endpoint defaults to None

- **WHEN** `WorkshopEndpointCapability(name="inference", host_endpoint="localhost:8080")` is instantiated without `container_endpoint`
- **THEN** `cap.container_endpoint` is `None`

---

### Requirement: Config type discriminator is `endpoint-proxy`

A YAML config entry with `type: endpoint-proxy` MUST deserialize to a `WorkshopEndpointCapability` instance via the `dec_hook` in `microjail.py`. The `name`, `host_endpoint`, and optionally `container_endpoint` fields MUST be preserved.

#### Scenario: Config round-trip with both endpoints (port remap)

- **WHEN** the config YAML contains `- type: endpoint-proxy\n  name: inference\n  host_endpoint: 127.0.0.1:8080\n  container_endpoint: 127.0.0.1:9090` under `lockdown.caps`
- **AND** `MicroJail.load(project_path)` is called
- **THEN** `microjail.lockdown.caps[0]` is a `WorkshopEndpointCapability` with `name="inference"`, `host_endpoint="127.0.0.1:8080"`, and `container_endpoint="127.0.0.1:9090"`

#### Scenario: Config round-trip without container endpoint

- **WHEN** the config YAML contains `- type: endpoint-proxy\n  name: inference\n  host_endpoint: localhost:8080` under `lockdown.caps`
- **AND** `MicroJail.load(project_path)` is called
- **THEN** `microjail.lockdown.caps[0]` is a `WorkshopEndpointCapability` with `name="inference"`, `host_endpoint="localhost:8080"`, and `container_endpoint` is `None`

## ADDED Requirements

### Requirement: resolved_endpoint returns the effective container-side address

`WorkshopEndpointCapability` SHALL provide a `resolved_endpoint` property that returns `container_endpoint` if not `None`, otherwise `host_endpoint`. This is the address the workload uses inside the container.

#### Scenario: resolved_endpoint returns container_endpoint when set

- **WHEN** `cap = WorkshopEndpointCapability(name="svc", host_endpoint="127.0.0.1:8080", container_endpoint="127.0.0.1:9090")`
- **THEN** `cap.resolved_endpoint == "127.0.0.1:9090"`

#### Scenario: resolved_endpoint returns host_endpoint when container_endpoint is None

- **WHEN** `cap = WorkshopEndpointCapability(name="svc", host_endpoint="localhost:8080")`
- **THEN** `cap.resolved_endpoint == "localhost:8080"`
