## Why

A workload running inside the microjail container can currently reach its own `.microjail/config.yaml` through the existing project directory mount and overwrite it — removing gates, adding capabilities, or corrupting the policy that the Warden is enforcing. Preventing in-container config mutation closes this self-modification attack surface before any workload runs.

## What Changes

- New gate `ReadonlyConfig` added to `src/microjail/gates/readonly_config.py`.
- Gate is included in `Lockdown.default()` alongside `NetworkDrop`.
- `lockdown.py` and `microjail.py` updated to import and recognise the new struct for serialisation.
- Unit tests covering `check`, `enforce`, and `release` semantics.
- Functional tests verifying end-to-end that the gate blocks writes to the config inside a real container and that releasing it restores write access.

## Capabilities

### New Capabilities

- `readonly-config`: Bind-mounts the microjail config file (`config.yaml`) into the container as a read-only LXC disk device, preventing any process inside the container from writing to it.

### Modified Capabilities

_(none — no existing spec-level requirements change)_

## Impact

- `src/microjail/gates/readonly_config.py` — new file
- `src/microjail/gates/__init__.py` — export updated
- `src/microjail/lockdown.py` — default lockdown includes the new gate
- `src/microjail/microjail.py` — msgspec union for `Gate` gains the new type
- `tests/unit/test_readonly_config.py` — new unit test file
- `tests/unit/test_lockdown.py` — default lockdown assertions updated
- `tests/functional/gates/test_readonly_config.py` — new functional test file
- No new dependencies; uses existing `lxc` and `workshop` adapters
