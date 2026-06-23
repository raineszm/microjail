# Capability: readonly-config (delta)

This file modifies the existing `openspec/specs/readonly-config/spec.md` to add a `verify()` method to the `ReadonlyConfig` gate. The gate has no behavioral probe; the `verify()` method is a no-op that returns `True`. The end-to-end behavior (the bind mount is read-only after `enforce()`) is unchanged.

## ADDED Requirements

### Requirement: verify returns True since the gate has no behavioral probe
`ReadonlyConfig.verify(microjail)` MUST return `True` unconditionally. The gate's enforcement (a read-only LXC disk device) is verified at the config level by `check()` and is not subject to a behavioral probe. The method is required by the `Gate` protocol so that `pre_launch_verify` can iterate all gates uniformly; for this gate, the probe is a no-op.

#### Scenario: verify does not raise on missing container
- **WHEN** `ReadonlyConfig.verify(microjail)` is called and the workshop container does not exist
- **THEN** the return value is `True` and no exception is raised
