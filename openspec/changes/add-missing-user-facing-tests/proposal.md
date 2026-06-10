## Why

Implemented and documented Microjail commands currently lack end-to-end and functional coverage for several safety-critical user-facing contracts. The missing tests allow regressions or known implementation gaps to persist around initialization, adoption, policy failure handling, endpoint-capability usage, explicit unlock, and command-specific policy semantics.

## What Changes

- Add e2e tests for the common implemented Microjail user journeys:
  - fresh `init` writes usable config and `lock` applies default Gates,
  - `init --adopt` binds an existing Workshop to Microjail and `lock` applies defaults,
  - `run` applies all implemented default Gates before workload start,
  - `run` leaves policy applied after workload exit,
  - `unlock` releases implemented policy effects,
  - `run` with a declared Endpoint capability reaches the declared host service while undeclared egress remains denied,
  - `run` refuses to start a workload when a declared Endpoint capability cannot be applied,
  - a shallow full lifecycle smoke path covers `init → run → still locked → unlock`.
- Add functional command tests for interaction contracts that do not require real Workshop/LXD:
  - `init` and `init --adopt` config-writing behavior,
  - command-specific capability/gate failure semantics for `lock` and `run`,
  - policy-result exit codes for implemented application and release phases,
  - concise output summaries and counts,
  - rollback and partial-application behavior,
  - documented config schema loading through CLI command paths,
  - release/revoke aggregation on `unlock`.
- Keep e2e focused on common and safety-critical user scenarios; keep broader branch matrices in functional tests.
- Exclude future or unimplemented features from this change: Warden runtime monitoring, `destroy`, `--force`, CTF escape testing, undeclared-state cleanup, existing-tunnel adoption declaration flows, and unimplemented secure-default Gates.

## Capabilities

### New Capabilities
- `user-facing-test-coverage`: Coverage requirements for implemented Microjail command behavior across e2e user journeys and functional interaction contracts.

### Modified Capabilities
- *(none — this change adds test coverage for existing implemented/documented behavior without changing product requirements.)*

## Impact

- **Added/modified tests**: `tests/e2e/`, `tests/functional/commands/`, and shared test helpers as needed.
- **Expected failures before implementation fixes**: Some new tests are intentionally expected to expose current implementation gaps, especially `init` config creation, `init --adopt` config creation, command-specific capability failure handling, bitmask policy exit codes, and CLI `unlock` release after a separate `lock` invocation.
- **No new runtime dependencies**.
- **No product CLI surface expansion**; future features remain out of scope.
