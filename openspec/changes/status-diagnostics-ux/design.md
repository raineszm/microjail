## Context

MicroJail has no command to inspect current state or validate configuration without applying policy. Users currently must:
- Read `.microjail/config.yaml` to see the declared lockdown policy
- Run `workshop info` separately to check workshop status
- Run `worshop connections` to see live tunnel state
- Read LXD container info to check runtime state
- Discover validation errors only when `lock` or `exec` fails

Both `status` and `validate` are read-only — no policy state is modified.

## Goals / Non-Goals

**Goals:**
- Add `microjail status` showing initialization state, workshop name/status, declared capabilities, declared gates, and live Workshop tunnel connections.
- Add `microjail validate` checking two things:
  a) **Schema conformance** — the config YAML matches the expected struct shapes (handled by `MicroJail.load()` / msgspec decode).
  b) **Semantic correctness** — the values are internally consistent: no duplicate cap names, valid endpoint names and addresses.
- Use existing `MicroJail.load()` — failure to load means either "not initialized" (no file) or "schema error" (bad YAML/struct mismatch).
- Keep output actionable: each error or warning includes what is wrong and recommends a next command.

**Non-Goals:**
- No policy state modification (read-only).
- No live enforcement or capability provide/revoke.
- No gate-specific validation beyond what `MicroJail.load()` already provides via msgspec deserialization.
- No performance monitoring or metrics beyond current state.
- No supervision or workload detection — those are future concerns.

## Decisions

### Decision 1: Single-file commands, not separate modules

The existing pattern in `src/microjail/commands/` is one file per command (`lock.py`, `init.py`, etc.). `status` and `validate` are small enough to live in their own files. Follow the existing pattern.

**Chosen**: `src/microjail/commands/status.py` and `src/microjail/commands/validate.py`.

### Decision 2: `MicroJail.validate()` returns a list of errors, `MicroJail.status()` returns a dataclass

`validate()` needs to report multiple independent issues. A list of structured error/ warning objects is more testable than printing directly. `status()` needs to return multiple named fields — a dataclass is natural.

**Chosen**:
- `ValidateError(msgspec.Struct)` with `kind: str` (e.g. `"duplicate_name"`, `"endpoint_syntax"`), `message: str`, `hint: str` (the next command to run).
- `MicroJailStatus(msgspec.Struct)` with fields: `initialized: bool`, `workshop_name: str`, `workshop_status: str`, `capabilities: list[str]`, `gates: list[str]`, `connections: list[str]`.

### Decision 3: Validate checks schema conformance and semantic rules

Two-tier validation:

1. **Schema conformance** — `MicroJail.load()` decodes the YAML through msgspec. If the file is missing, that's "not initialized." If the file exists but has a type error (wrong field type, unknown tag), msgspec raises `ValidationError` — caught and reported as a config error.
2. **Semantic correctness** — If load succeeds, iterate the decoded lockdown and run the existing validation functions:
   - `cap.py:validate_no_duplicate_names()` for duplicate capability names
   - `endpoint.py:validate_endpoint_name()` for endpoint capability names
   - `endpoint.py:validate_endpoint_address()` for endpoint addresses

Gates have no standalone semantic validation — their field types are already checked by msgspec at load time.

**Chosen**: `MicroJail.validate()` calls `load()` first, then runs semantic checks on the loaded config. Errors from either tier are collected and returned.

### Decision 4: status reads workshop info and tunnel connections for live state

`workshop info` and `workshop connections` are already available through the Workshop adapter. Status calls these to report live daemon state alongside declared policy.

**Chosen**: `MicroJail.status()` calls `self.workshop.info()`, `self.workshop.tunnel.connections()`, and reads `self.lockdown` for declared state.

## Risks / Trade-offs

- **Workshop daemon unreachable**: `workshop info` or `workshop connections` failing is handled gracefully — status reports "unavailable" rather than crashing.
- **Not initialized**: `MicroJail.load()` fails with `ConfigNotFoundError`. `microjail status` catches this and reports "not initialized (run `microjail init`)". `microjail validate` also catches this but exits non-zero (nothing to validate).
- **Validate scope stays narrow**: Validate does not re-implement every check lock performs. Only schema conformance + the semantic checks listed above. If lock gains new validations, validate may need updating — documented as a known gap.
