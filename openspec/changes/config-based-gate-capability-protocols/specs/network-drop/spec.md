## ADDED Requirements

### Requirement: check reflects NIC presence in expanded devices
`NetworkDrop.check(microjail)` MUST return `True` if and only if the workshop container's `expanded_devices` contains no entries of `type: nic`. The check is a config-state check only; it does not perform a behavioral probe. `check()` MUST return `False` (not raise) when the container is unavailable or the LXD query fails.

#### Scenario: check returns True when no NICs are present
- **GIVEN** the workshop container is running with no network devices in its `expanded_devices`
- **WHEN** `NetworkDrop.check(microjail)` is called
- **THEN** the return value is `True`

#### Scenario: check returns False when a NIC is present
- **GIVEN** the workshop container has a device of `type: nic` in its `expanded_devices`
- **WHEN** `NetworkDrop.check(microjail)` is called
- **THEN** the return value is `False`

#### Scenario: check returns False when container is unavailable
- **GIVEN** the workshop container does not exist or the LXD query fails
- **WHEN** `NetworkDrop.check(microjail)` is called
- **THEN** the return value is `False` and no exception is raised

### Requirement: verify returns True since the gate has no behavioral probe
`NetworkDrop.verify(microjail)` MUST return `True` unconditionally. The gate's enforcement (NIC removal) is verified at the config level by `check()` and is not subject to a behavioral probe. The method is required by the `Gate` protocol so that `pre_launch_verify` can iterate all gates uniformly; for this gate, the probe is a no-op.

#### Scenario: verify returns True unconditionally
- **WHEN** `NetworkDrop.verify(microjail)` is called
- **THEN** the return value is `True` and no exception is raised
