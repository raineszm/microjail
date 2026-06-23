## Purpose

The `WorkshopEndpointCapability` exposes a host:port endpoint from inside the workshop container to the microjail project via a Workshop tunnel. It manages the full lifecycle: declaring plugs and slots, establishing the tunnel connection, verifying reachability, and tearing down on revoke.

---
## Requirements
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

`WorkshopEndpointCapability.check(microjail)` MUST return `True` if and only if the Workshop tunnel connection (`<workshop>/microjail:<name>` → `<workshop>/system:<name>`) appears in `workshop connections` output. The check MUST NOT perform a TCP reachability probe; reachability is verified separately by `verify()`. If the tunnel connection is not present, `check()` MUST return `False`. `check()` MUST NOT raise.

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

#### Scenario: check does not perform a TCP probe

- **WHEN** the tunnel connection is present in `workshop connections`
- **AND** the host service at the resolved endpoint is unreachable (e.g. the upstream process has crashed)
- **AND** `WorkshopEndpointCapability.check(microjail)` is called
- **THEN** the return value is `True` (the check is config-state only; reachability is the responsibility of `verify()`)

---

### Requirement: provide is idempotent

`WorkshopEndpointCapability.provide(microjail)` MUST be safe to call when the capability is already satisfied. If `check()` returns `True`, `provide()` MUST succeed without attempting to re-add declarations or re-connect the tunnel.

#### Scenario: provide succeeds when already connected

- **WHEN** the tunnel is already connected and the endpoint is reachable
- **AND** `WorkshopEndpointCapability.provide(microjail)` is called
- **THEN** no error is raised

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

### Requirement: provide establishes the tunnel connection

`WorkshopEndpointCapability.provide(microjail)` MUST call `workshop refresh` to apply the updated definitions, then call `workshop connect <workshop>/microjail:<name> <workshop>/system:<name>` to establish the connection. The connection is a runtime connection and is not preserved across future refreshes.

#### Scenario: provide establishes the tunnel connection

- **WHEN** `WorkshopEndpointCapability.provide(microjail)` is called on a launched workshop
- **THEN** `workshop connections` output includes a `tunnel` row for `<workshop>/microjail:<name>` → `<workshop>/system:<name>`

---

### Requirement: revoke disconnects before removing declarations

`WorkshopEndpointCapability.revoke(microjail)` MUST disconnect the tunnel before modifying any files, then remove the plug from `.workshop/microjail/sdk.yaml` and the slot from the `system` SDK in `.workshop/<workshop-name>.yaml`, then call `workshop refresh`. If no plugs remain in `sdk.yaml` after removal, `project-microjail` MUST also be removed from the `sdks` list. The operation MUST be idempotent: absent connection or absent declarations are treated as no-ops.

#### Scenario: revoke removes the connection

- **WHEN** `WorkshopEndpointCapability.provide(microjail)` has been called
- **AND** `WorkshopEndpointCapability.revoke(microjail)` is called
- **THEN** `workshop connections` output no longer contains a tunnel row for `self.name`

#### Scenario: revoke removes plug from sdk.yaml

- **WHEN** `WorkshopEndpointCapability.revoke(microjail)` has been called
- **THEN** `.workshop/microjail/sdk.yaml` does not contain a plug keyed `self.name`

#### Scenario: revoke removes project-microjail when last capability is revoked

- **WHEN** `WorkshopEndpointCapability.revoke(microjail)` is called and `self.name` was the only plug in `.workshop/microjail/sdk.yaml`
- **THEN** `project-microjail` is removed from the workshop definition's `sdks` list

#### Scenario: revoke preserves other capabilities in sdk.yaml

- **WHEN** `WorkshopEndpointCapability.revoke(microjail)` is called and other plugs remain in `.workshop/microjail/sdk.yaml`
- **THEN** those other plugs are unchanged
- **AND** `project-microjail` remains in the workshop definition's `sdks` list

#### Scenario: revoke is idempotent when not connected

- **WHEN** `WorkshopEndpointCapability.revoke(microjail)` is called without a prior `provide()`
- **THEN** no error is raised

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

### Requirement: Config type discriminator is `endpoint-tunnel`

A YAML config entry with `type: endpoint-tunnel` MUST deserialize to a `WorkshopEndpointCapability` instance via the `dec_hook` in `microjail.py`. The `name`, `host_endpoint`, and optionally `container_endpoint` fields MUST be preserved.

#### Scenario: Config round-trip with both endpoints (port remap)

- **WHEN** the config YAML contains `- type: endpoint-tunnel\n  name: inference\n  host_endpoint: 127.0.0.1:8080\n  container_endpoint: 127.0.0.1:9090` under `lockdown.caps`
- **AND** `MicroJail.load(project_path)` is called
- **THEN** `microjail.lockdown.caps[0]` is a `WorkshopEndpointCapability` with `name="inference"`, `host_endpoint="127.0.0.1:8080"`, and `container_endpoint="127.0.0.1:9090"`

#### Scenario: Config round-trip without container endpoint

- **WHEN** the config YAML contains `- type: endpoint-tunnel\n  name: inference\n  host_endpoint: localhost:8080` under `lockdown.caps`
- **AND** `MicroJail.load(project_path)` is called
- **THEN** `microjail.lockdown.caps[0]` is a `WorkshopEndpointCapability` with `name="inference"`, `host_endpoint="localhost:8080"`, and `container_endpoint` is `None`

---

### Requirement: resolved_endpoint returns the effective container-side address

`WorkshopEndpointCapability` SHALL provide a `resolved_endpoint` property that returns `container_endpoint` if not `None`, otherwise `host_endpoint`. This is the address the workload uses inside the container.

#### Scenario: resolved_endpoint returns container_endpoint when set

- **WHEN** `cap = WorkshopEndpointCapability(name="svc", host_endpoint="127.0.0.1:8080", container_endpoint="127.0.0.1:9090")`
- **THEN** `cap.resolved_endpoint == "127.0.0.1:9090"`

#### Scenario: resolved_endpoint returns host_endpoint when container_endpoint is None

- **WHEN** `cap = WorkshopEndpointCapability(name="svc", host_endpoint="localhost:8080")`
- **THEN** `cap.resolved_endpoint == "localhost:8080"`

---

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

---

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

---

### Requirement: Stale endpoint cleanup is not rolled back

When stale Microjail-owned endpoint cleanup succeeds and a later Capability or Gate operation fails, the system MUST NOT restore the stale endpoint declaration during rollback.

#### Scenario: Failed run does not restore stale endpoint
- **GIVEN** Lockdown application removes a stale Microjail-owned endpoint declaration
- **AND** a later declared Capability fails before workload start during `microjail run`
- **WHEN** Microjail rolls back state applied during that failed run attempt
- **THEN** the stale endpoint declaration remains removed

---

### Requirement: verify reflects reachability state

`WorkshopEndpointCapability.verify(microjail)` MUST return `VerificationResult.VERIFIED` if a TCP connection to the resolved endpoint (`container_endpoint` if set, otherwise `host_endpoint`) succeeds from inside the workshop container. If the TCP connection fails, times out, or raises any exception (including `subprocess.CalledProcessError`, `subprocess.TimeoutExpired`, `ValueError`), `verify()` MUST return `VerificationResult.FAILED` rather than propagating the exception.

#### Scenario: verify returns VERIFIED when endpoint is reachable

- **WHEN** the host service at the resolved endpoint is reachable
- **AND** `WorkshopEndpointCapability.verify(microjail)` is called
- **THEN** the return value is `VerificationResult.VERIFIED`

#### Scenario: verify returns FAILED when endpoint is unreachable

- **WHEN** the host service at the resolved endpoint is not reachable (e.g. the upstream process has crashed or the port is closed)
- **AND** `WorkshopEndpointCapability.verify(microjail)` is called
- **THEN** the return value is `VerificationResult.FAILED`

#### Scenario: verify returns FAILED when tunnel is not connected

- **WHEN** the tunnel connection is not present in `workshop connections`
- **AND** `WorkshopEndpointCapability.verify(microjail)` is called
- **THEN** the return value is `VerificationResult.FAILED`

#### Scenario: verify does not propagate subprocess errors

- **WHEN** the underlying reachability probe raises `subprocess.CalledProcessError` or `subprocess.TimeoutExpired`
- **AND** `WorkshopEndpointCapability.verify(microjail)` is called
- **THEN** the return value is `VerificationResult.FAILED` and no exception is raised
