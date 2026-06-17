## Purpose

The `user-facing-test-coverage` capability ensures that the project provides comprehensive test coverage for user-facing CLI commands and workflows. This includes slow e2e tests that prove real Workshop-backed projects work end-to-end, and functional tests that verify command-layer behavior without requiring real Workshop/LXD execution.

---

## Requirements

### Requirement: E2E tests cover initialization and adoption user journeys

The project MUST provide slow e2e coverage proving that implemented initialization commands create usable Microjail configuration for real Workshop-backed projects.

#### Scenario: Fresh initialization produces lockable Microjail config

- **WHEN** `microjail init <name>` is run in a fresh project and the resulting Workshop is launched
- **THEN** `.microjail/config.yaml` exists and `microjail lock` applies the implemented default Gates

#### Scenario: Adoption produces lockable Microjail config

- **WHEN** an existing Workshop project with no pre-existing tunnels is launched and `microjail init <name> --adopt` is run
- **THEN** `.microjail/config.yaml` exists for that Workshop and `microjail lock` applies the implemented default Gates

---

### Requirement: E2E tests cover common run lifecycle safety

The project MUST provide slow e2e coverage proving that `microjail run` applies implemented policy before workload start and does not release policy after workload exit.

#### Scenario: Run applies readonly-config Gate before workload

- **WHEN** `microjail run -- <command>` executes a workload that attempts to append to `/project/.microjail/config.yaml`
- **THEN** the write is rejected by the readonly-config Gate and the workload reports failure

#### Scenario: Run leaves policy applied after workload exit

- **WHEN** `microjail run -- true` completes successfully under the default Lockdown
- **THEN** implemented default Gate effects remain applied until `microjail unlock` is run

#### Scenario: Run preserves Workshop project mount behavior

- **WHEN** `microjail run -- <command>` reads a normal project file from `/project` and writes a normal project output file
- **THEN** the project file workflow succeeds while implemented Microjail Gates remain applied

#### Scenario: Run auto-launches workshop if not launched

- **GIVEN** a microjail-configured project where the workshop has not been launched
- **WHEN** `microjail exec -- true` is run
- **THEN** the workshop is automatically launched
- **AND** the command completes successfully

---

### Requirement: E2E tests cover explicit unlock behavior

The project MUST provide slow e2e coverage proving that `microjail unlock` releases implemented policy effects that were applied through the user-facing CLI.

#### Scenario: Unlock releases default Gate effects

- **WHEN** `microjail lock` has applied the default Lockdown through the CLI
- **THEN** `microjail unlock` restores baseline network-egress and config-write behavior where the Workshop baseline supports those operations

#### Scenario: Repeated lock and unlock remain safe

- **WHEN** a user repeats `microjail lock` or `microjail unlock` after the target policy state is already reached
- **THEN** the command succeeds and the observed policy state remains correct

---

### Requirement: E2E tests cover Endpoint capability user journeys

The project MUST provide slow e2e coverage for declared Endpoint capability behavior through user configuration and CLI commands.

#### Scenario: Run reaches declared endpoint and blocks undeclared egress

- **WHEN** `.microjail/config.yaml` declares an Endpoint capability and `microjail run -- <command>` executes a workload that connects to that endpoint
- **THEN** the workload reached the declared endpoint and undeclared external network egress remains denied

#### Scenario: Run refuses workload start when Endpoint capability cannot be applied

- **WHEN** `.microjail/config.yaml` declares an Endpoint capability whose endpoint cannot be reached and `microjail run -- <command>` is invoked
- **THEN** Microjail returns a policy failure and the workload command does not start

#### Scenario: Unlock revokes declared Endpoint capability

- **WHEN** a declared Endpoint capability has been provided by a user-facing command
- **THEN** `microjail unlock` revokes that Endpoint capability separately from the test that proves the endpoint can be used during `run`

#### Scenario: CLI-added endpoint capability is usable during run

- **WHEN** `microjail cap add endpoint inference <host-endpoint>` adds an Endpoint Capability declaration
- **AND** `microjail run -- <command>` executes a workload that connects to that endpoint
- **THEN** the workload reaches the declared endpoint
- **AND** undeclared external network egress remains denied

---

### Requirement: E2E tests include one common lifecycle smoke path

The project MUST provide one shallow e2e smoke test covering the common user sequence across implemented commands.

#### Scenario: Full lifecycle smoke path

- **WHEN** a user runs `microjail init <name>`, launches Workshop, runs a workload with `microjail run`, observes policy still applied, and then runs `microjail unlock`
- **THEN** the workload can complete useful project file work, the policy remains applied after `run`, and `unlock` releases implemented policy effects

---

### Requirement: Functional tests cover command initialization contracts

The project MUST provide functional command tests for initialization behavior that does not require real Workshop/LXD execution.

#### Scenario: Init writes default Microjail config

- **WHEN** `microjail init <name>` succeeds through the command layer
- **THEN** the command writes `.microjail/config.yaml` with zero Capabilities and only implemented default Gates

#### Scenario: Adopt writes Microjail config for existing Workshop

- **WHEN** `microjail init <name> --adopt` is run for an existing Workshop
- **THEN** the command writes `.microjail/config.yaml` bound to that Workshop

#### Scenario: Init reports Workshop failures

- **WHEN** Workshop initialization fails through the adapter
- **THEN** `microjail init` exits non-zero with an operator-facing error and does not pretend the project is configured

#### Scenario: Init forwards --sdks flag to Workshop adapter

- **WHEN** `microjail init <name> --sdks golang` succeeds through the command layer
- **THEN** the `workshop.init` adapter is called with a `sdks` list that includes both `"golang"` and the default `"direnv"`

#### Scenario: Init forwards --base flag to Workshop adapter

- **WHEN** `microjail init <name> --base ubuntu@22.04` succeeds through the command layer
- **THEN** the `workshop.init` adapter is called with `base="ubuntu@22.04"`

#### Scenario: Init with no --base omits the flag from the adapter call

- **WHEN** `microjail init <name>` succeeds through the command layer without `--base`
- **THEN** the `workshop.init` adapter is called with `base=None`

#### Scenario: Adopt with --base warns

- **WHEN** `microjail init <name> --adopt --base ubuntu@22.04` is run for an existing Workshop
- **THEN** the command succeeds and emits a warning that `--base` is ignored during adopt

#### Scenario: --project flag resolves and is forwarded to commands

- **WHEN** `microjail init <name> --project /tmp/myproject` succeeds through the command layer
- **THEN** the command writes `.microjail/config.yaml` at `/tmp/myproject/.microjail/config.yaml`

#### Scenario: --project flag on lock uses the resolved project path

- **WHEN** `microjail lock --project /tmp/myproject` succeeds through the command layer
- **THEN** `MicroJail.load()` is called with `/tmp/myproject` and the Lockdown is applied against that project

---

### Requirement: Functional tests cover command-specific policy failure semantics

The project MUST provide functional tests proving `lock` and `run` handle capability and Gate application failures according to their distinct command semantics.

#### Scenario: Run blocks workload on capability application failure

- **WHEN** a required Capability cannot be applied during `microjail run`
- **THEN** the workload is not started and Gate enforcement for that run does not proceed after the blocking capability failure

#### Scenario: Lock continues to Gates after capability application failure

- **WHEN** a required Capability cannot be applied during `microjail lock`
- **THEN** Microjail still attempts implemented Gate enforcement and reports an incomplete non-zero result

#### Scenario: Run blocks workload on Gate application failure

- **WHEN** a Gate cannot be applied during `microjail run`
- **THEN** the workload is not started and the command returns a policy failure

#### Scenario: Lock stops before Gates on stale endpoint cleanup failure

- **WHEN** stale Microjail-owned Endpoint declaration cleanup fails during `microjail lock`
- **THEN** Microjail reports a Capability application failure
- **AND** Gate enforcement is not attempted

---

### Requirement: Functional tests cover policy result exit codes and output summaries

The project MUST provide functional tests for implemented policy-result exit codes and concise CLI summaries.

#### Scenario: Implemented application and release failures use policy bitmask codes

- **WHEN** command-level tests simulate capability application, Gate application, capability release, Gate release, or combined release failures
- **THEN** Microjail returns the documented implemented policy-result bitmask code for that phase and failure class

#### Scenario: Successful workload exit code passes through

- **WHEN** `microjail run` successfully applies policy and the workload exits with a non-zero code
- **THEN** Microjail passes through the workload exit code rather than replacing it with a policy code

#### Scenario: Lock and unlock summaries expose counts and failure names

- **WHEN** `microjail lock` or `microjail unlock` completes, partially completes, or fails in functional command tests
- **THEN** the command output includes the intended result wording, relevant counts, and failure names without traceback leakage

---

### Requirement: Functional tests cover rollback, partial application, and release aggregation

The project MUST provide functional tests for policy cleanup semantics that are too branch-heavy for e2e coverage.

#### Scenario: Run rolls back state applied during failed policy application

- **WHEN** `microjail run` applies some policy state and then encounters a later policy application failure before workload launch
- **THEN** Microjail rolls back policy state applied during that failed run attempt

#### Scenario: Lock leaves safest reachable posture after partial failure

- **WHEN** `microjail lock` successfully enforces some Gates but the full configured Lockdown is not satisfied
- **THEN** Microjail does not rollback successfully applied policy state merely because the lock result is incomplete or failed

#### Scenario: Unlock attempts all configured release operations

- **WHEN** one release or revoke operation fails during `microjail unlock`
- **THEN** Microjail attempts remaining configured release and revoke operations and reports all failures together

---

### Requirement: Functional tests cover documented config schema through CLI paths

The project MUST provide functional tests proving the documented YAML configuration shape is loaded correctly by user-facing commands.

#### Scenario: Endpoint capability config shape reaches command policy application

- **WHEN** `.microjail/config.yaml` contains a documented Endpoint capability entry with `type: endpoint-tunnel`, `name`, and `host_endpoint`
- **THEN** a CLI command load path constructs the Endpoint capability and includes it in policy application

#### Scenario: Duplicate Capability names are rejected before policy application

- **WHEN** `.microjail/config.yaml` contains two Capability entries with the same `name`
- **THEN** a CLI command load path reports a config validation error before applying policy

#### Scenario: Invalid Endpoint syntax is rejected before policy application

- **WHEN** `.microjail/config.yaml` contains an Endpoint capability entry whose endpoint fields are not valid simple `HOST:PORT` values
- **THEN** a CLI command load path reports a config validation error before applying policy

#### Scenario: Default Gate config shape reaches command policy application

- **WHEN** `.microjail/config.yaml` contains documented Gate entries for `network-egress` and `readonly-config`
- **THEN** a CLI command load path constructs those Gates and includes them in policy application

---

### Requirement: Functional tests cover Endpoint Capability CLI commands

The project MUST provide functional command tests for `microjail cap add endpoint` and `microjail cap remove endpoint` behavior that does not require real Workshop/LXD execution.

#### Scenario: Cap add endpoint writes config

- **GIVEN** a configured Microjail project whose Workshop state permits declaration editing
- **WHEN** `microjail cap add endpoint inference localhost:8080` is run through the command layer
- **THEN** `.microjail/config.yaml` contains the Endpoint Capability declaration

#### Scenario: Cap add endpoint replace requires flag

- **GIVEN** `.microjail/config.yaml` already declares Endpoint Capability `inference`
- **WHEN** `microjail cap add endpoint inference localhost:9090` is run through the command layer
- **THEN** the command fails and leaves the config unchanged

#### Scenario: Cap remove endpoint writes config

- **GIVEN** `.microjail/config.yaml` declares Endpoint Capability `inference`
- **WHEN** `microjail cap remove endpoint inference` is run through the command layer
- **THEN** `.microjail/config.yaml` no longer declares Endpoint Capability `inference`

#### Scenario: Cap apply refuses locked state

- **GIVEN** a configured Microjail project whose Workshop is ready
- **AND** a current Gate check returns true
- **WHEN** a `microjail cap` command is run through the command layer
- **THEN** the command fails before saving and tells the user to unlock before editing Capability declarations

#### Scenario: Cap apply updates stopped declarations only

- **GIVEN** a configured Microjail project whose Workshop is stopped or off
- **WHEN** `microjail cap add endpoint inference localhost:8080 --apply` is run through the command layer
- **THEN** the command updates Microjail and Workshop declaration files
- **AND** it does not start, refresh, or connect the Workshop
