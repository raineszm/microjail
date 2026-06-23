# Gate: network-drop (delta)

This file captures the behavioral change to the `NetworkDrop` gate under the warden-event-driven change. The gate already exists in code (`src/microjail/gates/network_drop.py`) and enforces network egress blocking by removing all NICs from the workshop container. This change replaces the bash-based egress probe in `check()` with a config-state check and adds a no-op `verify()` method.

## REMOVED Requirements

### Requirement: check performs a bash egress probe
**Reason:** The bash probe (`bash -c ": >/dev/tcp/1.1.1.1/443"`) was redundant with LXD's kernel-level NIC removal and bug-prone: it required bash inside the container, causing false-positive gate violations on minimal images (alpine, distroless, scratch). Under the threat model "LXD is the only thing that can enforce," the probe is unnecessary — the only way network access can be re-established is via an LXD configuration change, which the `lxc monitor` event stream detects. The probe is replaced by a config check (no devices of `type: nic` in `expanded_devices`).

**Migration:** Any test or integration that asserted the bash probe behavior (e.g. mocking `microjail.exec_` with `EGRESS_PROBE`) should instead assert the config check (mock `lxc_instance().expanded_devices` with no `type: nic` entries).

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
