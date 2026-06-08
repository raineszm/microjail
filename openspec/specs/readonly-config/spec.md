## Purpose

The `readonly-config` capability ensures that the microjail config file (`.microjail/config.yaml`) cannot be overwritten by any process running inside the workshop container. It is implemented as a gate that bind-mounts the config file read-only via an LXC disk device, preventing a workload from modifying its own security policy.

---

## Requirements

### Requirement: Config file is read-only inside the container

The `ReadonlyConfig` gate, when enforced, MUST ensure that the microjail config file (`config.yaml`) cannot be written to by any process running inside the workshop container.

#### Scenario: Enforce makes config file unwritable inside container

- **WHEN** `ReadonlyConfig.enforce(microjail)` is called on a running workshop container
- **THEN** a write attempt to `/project/.microjail/config.yaml` inside the container is rejected with a permission error

---

### Requirement: Check reflects current enforcement state

`ReadonlyConfig.check(microjail)` MUST return `True` if and only if the read-only bind mount is currently active on the container.

#### Scenario: Check returns false before enforcement

- **WHEN** `ReadonlyConfig.check(microjail)` is called before `enforce()` has been called
- **THEN** the return value is `False`

#### Scenario: Check returns true after enforcement

- **WHEN** `ReadonlyConfig.enforce(microjail)` has completed successfully
- **AND** `ReadonlyConfig.check(microjail)` is called
- **THEN** the return value is `True`

#### Scenario: Check returns false after release

- **WHEN** `ReadonlyConfig.release(microjail)` has completed
- **AND** `ReadonlyConfig.check(microjail)` is called
- **THEN** the return value is `False`

#### Scenario: Check returns false when container is not available

- **WHEN** `ReadonlyConfig.check(microjail)` is called and the workshop container does not exist
- **THEN** the return value is `False` and no exception is raised

---

### Requirement: Release restores the original mount state

`ReadonlyConfig.release(microjail)` MUST remove the read-only bind mount device, restoring the file to its prior (writable) visibility inside the container.

#### Scenario: Release removes the read-only device

- **WHEN** `ReadonlyConfig.enforce(microjail)` has been called
- **AND** `ReadonlyConfig.release(microjail)` is called
- **THEN** the LXC device named `microjail-config-ro` is removed from the container

#### Scenario: Release is idempotent when not enforced

- **WHEN** `ReadonlyConfig.release(microjail)` is called without a prior `enforce()`
- **THEN** no error is raised

---

### Requirement: Gate is included in the default lockdown

`Lockdown.default()` MUST include a `ReadonlyConfig` instance in its `gates` list.

#### Scenario: Default lockdown includes ReadonlyConfig

- **WHEN** `Lockdown.default()` is called
- **THEN** the returned lockdown's `gates` list contains a `ReadonlyConfig` instance

---

### Requirement: Gate has a stable name

`ReadonlyConfig.name` MUST be the string `"readonly-config"`.

#### Scenario: Gate name is correct

- **WHEN** `ReadonlyConfig()` is instantiated
- **THEN** `gate.name == "readonly-config"`
