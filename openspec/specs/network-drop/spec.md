## Purpose

The `NetworkDrop` Gate ensures that the workshop container has no network interfaces (NICs) attached, preventing the workload from making external network connections. It verifies this at the config level by inspecting the container's LXD device list.

---

## Requirements

### Requirement: check reflects NIC presence in the workshop container's devices

`NetworkDrop.check(microjail)` MUST return `True` if and only if the `InstanceInfo.devices` returned by `microjail.lxc_instance()` contains no entries of `type: nic`. (`InstanceInfo.devices` is populated from the LXD `expanded_devices` key; the requirement is stated in terms of the Python attribute the implementation actually consults.) The check is a config-state check only; it does not perform a behavioral probe. `check()` MUST return `False` (not raise) when the container is unavailable or the LXD query fails.

#### Scenario: check returns True when no NICs are present

- **GIVEN** the workshop container is running with no network devices in its `devices`
- **WHEN** `NetworkDrop.check(microjail)` is called
- **THEN** the return value is `True`

#### Scenario: check returns False when a NIC is present

- **GIVEN** the workshop container has a device of `type: nic` in its `devices`
- **WHEN** `NetworkDrop.check(microjail)` is called
- **THEN** the return value is `False`

#### Scenario: check returns False when container is unavailable

- **GIVEN** the workshop container does not exist or the LXD query fails
- **WHEN** `NetworkDrop.check(microjail)` is called
- **THEN** the return value is `False` and no exception is raised

---

### Requirement: verify returns UNSUPPORTED since the gate has no behavioral probe

`NetworkDrop.verify(microjail)` MUST return `VerificationResult.UNSUPPORTED` unconditionally. The gate's enforcement (NIC removal) is verified at the config level by `check()` and is not subject to a behavioral probe. The method is required by the `Gate` protocol so that `pre_launch_verify` can iterate all gates uniformly; for this gate, the probe is a no-op.

#### Scenario: verify returns UNSUPPORTED unconditionally

- **WHEN** `NetworkDrop.verify(microjail)` is called
- **THEN** the return value is `VerificationResult.UNSUPPORTED` and no exception is raised
