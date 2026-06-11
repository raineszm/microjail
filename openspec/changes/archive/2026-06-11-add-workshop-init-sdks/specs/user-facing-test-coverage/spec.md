## MODIFIED Requirements

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
