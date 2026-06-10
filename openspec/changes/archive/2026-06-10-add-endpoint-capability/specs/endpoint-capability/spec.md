## ADDED Requirements

### Requirement: Endpoint is reachable after provide

After `WorkshopEndpointCapability.provide(microjail)` completes, the declared `host:port` MUST be reachable from inside the workshop container at the same address.

#### Scenario: Endpoint reachable inside container after provide

- **WHEN** `WorkshopEndpointCapability.provide(microjail)` is called with a running workshop
- **THEN** a TCP connection to `host:port` from inside the container succeeds

---

### Requirement: check reflects connection and reachability state

`WorkshopEndpointCapability.check(microjail)` MUST return `True` if and only if both conditions hold:
1. The Workshop tunnel connection (`<workshop>/microjail:<name>` → `<workshop>/system:<name>`) appears in `workshop connections` output.
2. The declared `host:port` is reachable via TCP from inside the workshop container.

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

### Requirement: provide is idempotent

`WorkshopEndpointCapability.provide(microjail)` MUST be safe to call when the capability is already satisfied. If `check()` returns `True`, `provide()` MUST succeed without attempting to re-add declarations or re-connect the tunnel.

#### Scenario: provide succeeds when already connected

- **WHEN** the tunnel is already connected and the endpoint is reachable
- **AND** `WorkshopEndpointCapability.provide(microjail)` is called
- **THEN** no error is raised

---

### Requirement: provide writes plug to in-project SDK and slot to workshop definition

`WorkshopEndpointCapability.provide(microjail)` MUST write the plug declaration to `.workshop/microjail/sdk.yaml` (the in-project SDK owned by microjail) and add the corresponding slot to the `system` SDK in the workshop definition at `.workshop/<workshop-name>.yaml`. If `.workshop/microjail/sdk.yaml` does not exist it MUST be created. If `project-microjail` is not already listed in the workshop definition's `sdks`, it MUST be added.

#### Scenario: provide writes plug to in-project SDK file

- **WHEN** `WorkshopEndpointCapability.provide(microjail)` is called
- **THEN** `.workshop/microjail/sdk.yaml` contains a plug keyed `self.name` with `interface: tunnel` and `endpoint: self.endpoint` under the `plugs:` section

#### Scenario: provide adds system slot to workshop definition

- **WHEN** `WorkshopEndpointCapability.provide(microjail)` is called
- **THEN** `.workshop/<workshop-name>.yaml` contains a slot keyed `self.name` with `interface: tunnel` and `endpoint: self.endpoint` under the `system` SDK's `slots:` section

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

`WorkshopEndpointCapability.name` MUST equal the `name` string provided at construction. The name is used as the Workshop plug/slot identifier and MUST be a valid Workshop identifier (letters, digits, hyphens; starts with a letter).

#### Scenario: Capability name is preserved

- **WHEN** `WorkshopEndpointCapability(name="inference", endpoint="localhost:8080")` is instantiated
- **THEN** `cap.name == "inference"`

---

### Requirement: Config type discriminator is `endpoint-proxy`

A YAML config entry with `type: endpoint-proxy` MUST deserialize to a `WorkshopEndpointCapability` instance via the `dec_hook` in `microjail.py`. The `name` and `endpoint` fields MUST be preserved.

#### Scenario: Config round-trip produces correct capability

- **WHEN** the config YAML contains `- type: endpoint-proxy\n  name: inference\n  endpoint: localhost:8080` under `lockdown.caps`
- **AND** `MicroJail.load(project_path)` is called
- **THEN** `microjail.lockdown.caps[0]` is a `WorkshopEndpointCapability` with `name="inference"` and `endpoint="localhost:8080"`
