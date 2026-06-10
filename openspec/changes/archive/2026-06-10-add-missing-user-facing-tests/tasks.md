## 1. Shared Test Infrastructure

- [x] 1.1 Add or refactor e2e helpers for fresh Workshop project creation, CLI invocation from project cwd, Workshop launch/remove cleanup, and baseline skip handling without changing product behavior.
- [x] 1.2 Add e2e probe helpers for network egress, readonly-config writability, declared Endpoint reachability, and normal `/project` read/write behavior.
- [x] 1.3 Add a reusable host TCP listener fixture/helper for Endpoint capability e2e tests, following the existing passive listener pattern.
- [x] 1.4 Add functional command helper utilities for creating documented config files, invoking Typer commands from a temporary cwd, and recording fake Capability/Gate call order.
- [x] 1.5 Keep helper naming aligned with glossary terms: Endpoint capability, network-egress Gate, readonly-config Gate.

## 2. Functional Init and Config Contract Tests

- [x] 2.1 Add functional test proving `microjail init <name>` delegates to Workshop and writes `.microjail/config.yaml` with the Workshop name, project path, zero Capabilities, and implemented default Gates only.
- [x] 2.2 Add functional test proving `microjail init <name> --adopt` for an existing Workshop writes a usable `.microjail/config.yaml` bound to that Workshop.
- [x] 2.3 Add functional test proving `microjail init <name> --adopt` for a missing Workshop fails without writing Microjail config.
- [x] 2.4 Add functional test proving Workshop initialization failure exits non-zero with an operator-facing error and does not report successful Microjail configuration.
- [x] 2.5 Add functional test proving a documented config containing `type: endpoint-proxy`, `name`, and `endpoint` reaches the command policy application path as a `WorkshopEndpointCapability`.
- [x] 2.6 Add functional test proving documented `network-egress` and `readonly-config` Gate entries reach the command policy application path as Gates.

## 3. Functional Command Policy Semantics

- [x] 3.1 Add functional test proving `microjail run` returns a capability application policy failure and does not start the workload when a required Capability cannot be applied.
- [x] 3.2 Add functional test proving `microjail run` does not proceed to Gate enforcement after a blocking capability application failure.
- [x] 3.3 Add functional test proving `microjail lock` still attempts implemented Gate enforcement after a capability application failure and reports an incomplete non-zero result.
- [x] 3.4 Add functional test proving `microjail run` returns a Gate application policy failure and does not start the workload when a Gate cannot be applied.
- [x] 3.5 Add functional tests for implemented policy-result exit codes: capability application failure `66`, Gate application failure `68`, capability release failure `98`, Gate release failure `100`, and combined release failure `102`.
- [x] 3.6 Add functional test proving successful `microjail run` preserves workload exit-code passthrough when no policy failure occurs.
- [x] 3.7 Add functional tests for `lock` output summaries: success with `0 capabilities` and Gate count, incomplete capability failure with counts, and Gate failure with failed Gate name and no traceback.
- [x] 3.8 Add functional tests for `unlock` output summaries and failure diagnostics, including aggregated release failure names without traceback leakage.
- [x] 3.9 Add functional test proving `microjail run` rolls back policy state applied during a failed pre-workload policy application attempt.
- [x] 3.10 Add functional test proving `microjail lock` does not rollback successfully applied policy state merely because the final lock result is incomplete or failed.
- [x] 3.11 Add functional test proving `microjail unlock` attempts every configured Gate release and Capability revoke operation after failures and aggregates all failures.

## 4. P0 E2E User-Facing Vertical Slices

- [x] 4.1 Add e2e test `test_init_writes_default_config_that_lock_can_apply`: fresh `microjail init`, Workshop launch, `microjail lock`, then verify egress denied and config read-only.
- [x] 4.2 Add e2e test `test_init_adopt_existing_workshop_writes_config_and_lock_applies_defaults`: direct Workshop init/launch, `microjail init --adopt`, `microjail lock`, then verify implemented default Gates apply.
- [x] 4.3 Add e2e test `test_run_applies_readonly_config_gate_before_workload`: run a workload that appends to `/project/.microjail/config.yaml` and assert the write is denied.
- [x] 4.4 Add e2e test `test_run_does_not_unlock_after_workload_exits`: run `microjail run -- true`, then verify implemented default Gate effects remain applied.
- [x] 4.5 Add e2e test `test_unlock_releases_network_egress_and_readonly_config_gate`: apply default Lockdown through CLI, run `microjail unlock`, then verify baseline egress/config writability is restored when baseline supports it.
- [x] 4.6 Add e2e test `test_run_with_endpoint_capability_reaches_declared_endpoint_and_blocks_other_egress`: configure an Endpoint capability, run a workload that reaches it, and verify undeclared external egress remains denied.
- [x] 4.7 Add e2e test `test_run_does_not_start_workload_when_endpoint_capability_unreachable`: configure an unreachable Endpoint capability, run a marker-writing workload, and assert the marker is not created.
- [x] 4.8 Add e2e lifecycle smoke test covering `init → launch → run useful project file workload → verify policy still applied → unlock`.

## 5. P1 E2E Coverage

- [x] 5.1 Add e2e test proving repeated `microjail lock` succeeds and leaves policy enforced.
- [x] 5.2 Add e2e test proving repeated `microjail unlock` succeeds and leaves policy released.
- [x] 5.3 Add e2e test proving `microjail lock` followed by `microjail run -- true` succeeds without requiring a clean baseline.
- [x] 5.4 Add e2e test `test_run_preserves_workshop_project_mount_behavior` proving Microjail does not break Workshop's normal `/project` read/write workflow while Gates remain applied.
- [x] 5.5 Add e2e missing-config guidance tests for `lock`, `run`, and `unlock` with minimal assertions: non-zero exit plus guidance to initialize Microjail.
- [x] 5.6 Add e2e test proving `microjail unlock` revokes a declared Endpoint capability separately from Endpoint `run` provisioning/use coverage.

## 6. Verification and Scope Guardrails

- [x] 6.1 Run targeted fast functional tests for the command test files and helpers touched by this change.
- [x] 6.2 Run targeted e2e collection for new e2e files to verify markers and fixtures are wired correctly.
- [x] 6.3 In a capable environment, run the new slow e2e tests with `uv run pytest --slow tests/e2e` and record which failures expose existing implementation gaps rather than test harness defects.
- [x] 6.4 Confirm no tests were added for excluded future features: Warden runtime monitoring, `destroy`, `--force`, CTF escape testing, undeclared-state cleanup, existing-tunnel adoption declaration flows, or unimplemented secure-default Gates.
- [x] 6.5 Confirm active specs and test names consistently use Endpoint capability, network-egress Gate, and readonly-config Gate terminology.
