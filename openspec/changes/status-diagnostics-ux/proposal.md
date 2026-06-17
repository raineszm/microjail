## Why

After applying a lockdown policy, there is no built-in way to inspect what changed or verify the current state. Users must piece together information from multiple workshop commands and config files. `microjail status` and `microjail validate` provide a single-command view into initialization, workshop state, declared capabilities, gates, and config validity — making the system' s behavior observable and debugging actionable.

## What Changes

- Add `microjail status` command that shows initialization status, workshop state, declared capabilities with their resolution, gates with their enforcement state, and live policy state.
- Add `microjail validate` command that runs the same Lockdown/config validation used before `lock` (duplicate Capability names, endpoint syntax, gate config) without applying policy.
- Keep output actionable: show what is wrong and the next command to run.
- Both commands are read-only — no policy state is modified.

## Capabilities

### New Capabilities

- `status-command`: Read-only display of microjail and workshop state, capabilities, and gates.
- `validate-command`: Read-only validation of config and lockdown without applying policy.

### Modified Capabilities

None — no existing capability changes.

## Impact

- **src/microjail/cli.py**: Add `status` and `validate` CLI commands.
- **src/microjail/microjail.py**: Add `status()` and `validate()` methods to MicroJail.
- **tests/**: Unit and functional tests for both commands.
