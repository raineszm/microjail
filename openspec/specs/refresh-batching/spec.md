## Purpose

TBD — This spec captures the batching contract for `workshop refresh` and tunnel connect/disconnect operations when multiple endpoint capabilities are provided or revoked within a single `MicroJail.ensure()` or `MicroJail.release()` call.

---

## Requirements

### Requirement: Batch refresh across multiple endpoint capability provides

When `MicroJail.ensure()` is called with multiple `WorkshopEndpointCapability` declarations, the system SHALL issue at most one `workshop refresh` call across all provide operations. Each capability's plug and slot declarations SHALL be written to YAML immediately when `provide()` is called; the refresh and tunnel connect SHALL be deferred to the batch flush.

#### Scenario: Two endpoint capabilities trigger one refresh during ensure (LOCK)

- **GIVEN** a MicroJail with two declared `WorkshopEndpointCapability` declarations (`inference` and `storage`)
- **AND** neither capability is currently provided
- **WHEN** `MicroJail.ensure(ApplicationIntent.LOCK)` is called
- **THEN** each capability's plug and slot is written to YAML immediately during its `provide()` call
- **AND** the system calls `workshop refresh` exactly once after all provides have completed
- **AND** after refresh, both tunnels are connected

#### Scenario: Two endpoint capabilities trigger one refresh during ensure (RUN)

- **GIVEN** a MicroJail with two declared `WorkshopEndpointCapability` declarations (`inference` and `storage`)
- **AND** neither capability is currently provided
- **WHEN** `MicroJail.ensure(ApplicationIntent.RUN)` is called
- **THEN** the system calls `workshop refresh` exactly once
- **AND** after refresh, both tunnels are connected

#### Scenario: Single capability provide still works standalone

- **GIVEN** a `WorkshopEndpointCapability` instance
- **WHEN** `capability.provide(microjail)` is called directly (not through `ensure`)
- **THEN** YAML mutations are written immediately
- **AND** `workshop refresh` is called once
- **AND** the tunnel is connected

#### Scenario: Batch with zero capabilities skips refresh

- **GIVEN** a MicroJail with zero endpoint capabilities
- **WHEN** `MicroJail.ensure(ApplicationIntent.LOCK)` is called
- **THEN** no `workshop refresh` is called

---

### Requirement: Batch refresh across multiple endpoint capability revokes

When `MicroJail.release()` is called, the system SHALL issue at most one `workshop refresh` across all revoke operations. Each capability's tunnel SHALL be disconnected immediately, and its plug/slot declarations SHALL be removed from YAML immediately; only the refresh is deferred to batch flush.

#### Scenario: Two endpoint revokes trigger one refresh during release

- **GIVEN** a MicroJail with two provided endpoint capabilities
- **WHEN** `MicroJail.release()` is called
- **THEN** each tunnel is disconnected immediately during its `revoke()` call
- **AND** each capability's plug and slot is removed from YAML immediately
- **AND** the system calls `workshop refresh` exactly once after all revokes have completed

#### Scenario: Single capability revoke still works standalone

- **GIVEN** a provided `WorkshopEndpointCapability` instance
- **WHEN** `capability.revoke(microjail)` is called directly (not through `release`)
- **THEN** the tunnel is disconnected
- **AND** YAML mutations are written immediately
- **AND** `workshop refresh` is called once

---

### Requirement: Partial failure does not corrupt YAML state

When an exception occurs inside a batch context during `ensure()`, YAML mutations from preceding provide calls SHALL remain on disk. The daemon SHALL NOT be refreshed, so it never observes the partial state. A subsequent `ensure()` call SHALL succeed after the error is corrected.

#### Scenario: Exception in ensure leaves orphan YAML entries but daemon is untouched

- **GIVEN** a MicroJail with two declared endpoint capabilities (`inference` and `storage`)
- **AND** `storage` has an invalid endpoint address
- **WHEN** `MicroJail.ensure(ApplicationIntent.LOCK)` is called
- **THEN** `inference`'s plug and slot are written to YAML
- **AND** `storage`'s provide raises before writing
- **AND** `workshop refresh` is NOT called
- **AND** the daemon is unaware of `inference`'s declarations
- **WHEN** the user fixes `storage`'s endpoint and calls `ensure()` again
- **THEN** both capabilities are provided successfully with one refresh

---

### Requirement: Tunnel connect/disconnect execute during batch flush, after refresh

When a batch context is active, `workshop connect` and `workshop disconnect` SHALL NOT be called immediately. Instead, connect calls SHALL be deferred to the batch flush and SHALL execute after the single `workshop refresh`. Disconnect calls SHALL execute immediately before deferred refresh.

#### Scenario: Connect is deferred to batch flush and runs after refresh

- **GIVEN** a batch context wrapping the provide loop in `ensure`
- **WHEN** two capabilities are provided inside the batch
- **THEN** plug and slot are written to YAML immediately for each capability
- **AND** `workshop connect` is NOT called during either provide
- **WHEN** the batch context exits
- **THEN** `workshop refresh` is called once
- **AND** `workshop connect` is called twice (once per capability), after refresh

#### Scenario: Disconnect is immediate, plug/slot removal immediate, refresh deferred

- **GIVEN** a batch context wrapping the revoke loop in `release`
- **WHEN** two capabilities are revoked
- **THEN** `workshop disconnect` is called immediately for each capability
- **AND** plugs and slots are removed from YAML immediately
- **WHEN** the batch context exits
- **THEN** `workshop refresh` is called exactly once
