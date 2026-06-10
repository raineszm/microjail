## Context

Microjail already has unit, functional, and e2e tests, but coverage is uneven across the implemented command surface. Existing e2e tests prove selected Gate behavior and Endpoint capability API behavior, while several user-facing vertical slices remain untested or are only tested through mocks. Some intended contracts are documented in `DESIGN.md`, `README.md`, ADRs, and OpenSpec artifacts but are not yet enforced by tests; adding these tests is expected to expose current implementation gaps.

The key boundary for this change is test scope: e2e tests should exercise common and safety-critical user journeys against real Workshop/LXD, while functional tests should cover command interaction contracts, branch matrices, exit codes, output wording, and rollback semantics without incurring container cost.

## Goals / Non-Goals

**Goals:**
- Add e2e tests for implemented, documented user-facing command flows where real Workshop/LXD behavior matters.
- Add functional tests for implemented command contracts that can be proven with controlled fakes/mocks.
- Preserve current domain language: Endpoint capability is a declared Capability; `network-egress` and `readonly-config` are Gates.
- Make tests encode intended behavior from the active design/docs rather than downgrading expectations to current implementation bugs.
- Keep slow coverage small, behavior-focused, and reusable through shared helpers.

**Non-Goals:**
- Implement or test future features: Warden runtime monitoring, runtime policy violation exit codes, `destroy`, `--force`, CTF escape testing, undeclared-state cleanup, existing tunnel adoption declaration flows, or unimplemented secure-default Gates.
- Convert every functional branch into an e2e test.
- Add new runtime dependencies or change the public CLI surface as part of the test proposal.
- Stabilize `--overwrite`; tests for that branch are deferred until its semantics are documented or removed.

## Decisions

### 1. E2E tests cover common and safety-critical user journeys only

E2E tests will use real Workshop/LXD to verify behavior that mocks cannot prove: real config files, real Workshop launch/adoption, real Gate effects, real Endpoint tunnel reachability, and real post-command policy state.

Primary e2e coverage will include:
- `init` writes usable config and `lock` applies default Gates.
- `init --adopt` writes usable config for an existing Workshop and `lock` applies default Gates.
- `run` applies all implemented default Gates before workload start.
- `run` leaves policy applied after workload exit.
- `unlock` releases implemented policy effects.
- Endpoint-capability `run` reaches the declared endpoint while undeclared egress remains denied.
- Endpoint-capability application failure blocks workload start.
- One shallow full lifecycle smoke path.

**Alternative considered:** put all contract coverage in e2e. Rejected because it would make the slow suite brittle and expensive while duplicating branch coverage better handled by functional tests.

### 2. Functional tests own command contracts and failure matrices

Functional tests will cover command-level decisions without real containers: exit-code mapping, output summaries/counts, command-specific capability/gate failure behavior, rollback/partial-application semantics, documented config schema loading through CLI paths, and `unlock` aggregation.

**Alternative considered:** keep the existing mock tests as-is and only add e2e tests. Rejected because many current failures are interaction-contract problems, not substrate problems; they need fast, precise tests.

### 3. Tests intentionally expose implementation gaps

New tests should encode the active intended contract even when current code fails it. Examples include `init` writing `.microjail/config.yaml`, `init --adopt` writing config, `run` blocking workload launch on required capability failure, bitmask policy exit codes, and `unlock` releasing state after a separate CLI `lock` process.

**Alternative considered:** weaken tests to match current behavior. Rejected because the current behavior contradicts documented implemented commands and would hide safety regressions.

### 4. Shared helpers should isolate Workshop/LXD mechanics

E2E helpers should centralize:
- fresh project and Workshop lifecycle,
- CLI invocation from the project cwd,
- network-egress probes,
- readonly-config write probes,
- Endpoint listener/probe setup,
- `/project` mount read/write probes,
- cleanup through `workshop remove`.

This keeps individual e2e tests readable as user stories and reduces duplicated cleanup code.

**Alternative considered:** inline setup/teardown in each test file. Rejected because the existing e2e setup already repeats Workshop lifecycle details, and the new suite will add more scenarios.

### 5. Endpoint capability coverage is split by behavior

Endpoint `run` provisioning/use and Endpoint revocation on `unlock` should be separate tests. Provisioning failures should have a separate negative `run` test that proves the workload does not start.

**Alternative considered:** one large Endpoint lifecycle test. Rejected because a single failure would obscure whether provisioning, policy interaction, workload execution, or release broke.

### 6. Adoption coverage is limited to the simple existing-Workshop path

`init --adopt` tests should cover an existing Workshop with no pre-existing tunnels/connections. They should not cover declaration of existing tunnels, interactive adoption prompts, or undeclared connection cleanup because those flows are not implemented.

**Alternative considered:** test the full glossary definition of Workshop adoption now. Rejected because that would pull in unimplemented endpoint-adoption behavior explicitly excluded by the Endpoint capability design.

## Risks / Trade-offs

- **Risk:** New failing tests may be mistaken for regressions introduced by this test change. → **Mitigation:** Name tests and task descriptions clearly around current implementation gaps and intended contracts.
- **Risk:** E2E suite becomes slow or flaky due to repeated Workshop setup. → **Mitigation:** keep e2e count focused, centralize helpers, use skip conditions only for missing baseline substrate behavior, and leave broad matrices to functional tests.
- **Risk:** Output assertions become brittle. → **Mitigation:** assert detailed output in functional tests only; e2e assertions should prefer state and minimal operator guidance.
- **Risk:** Tests accidentally cover future features. → **Mitigation:** keep explicit exclusions in tasks and avoid adding `--force`, Warden, CTF, or undeclared-state scenarios.
- **Risk:** Endpoint tests depend on host networking details. → **Mitigation:** use the already-established host TCP listener pattern and Workshop tunnel reachability checks from existing tests.
