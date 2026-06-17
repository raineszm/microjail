## MODIFIED Requirements

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
