## Purpose

The `workshop-project-flag` capability defines the global `--project` / `-p` CLI flag that resolves to an absolute path and is threaded through all microjail commands and Workshop subprocess calls, decoupling command behavior from the process working directory.

---

## Requirements

### Requirement: Global --project flag resolves to absolute path

The `microjail` CLI SHALL accept a global `--project` / `-p` flag on all commands, resolve it to an absolute `Path`, and store it in the Typer context for command-level use. When `--project` is not provided, the current working directory SHALL be used as the project path.

#### Scenario: --project flag resolves relative path to absolute

- **GIVEN** the current working directory is `/home/user/work`
- **WHEN** `microjail init myproj --project ../other` is run
- **THEN** the project path resolved by the callback is `/home/user/other`

#### Scenario: --project flag accepts absolute path unchanged

- **GIVEN** an existing microjail-configured project at `/tmp/myproject`
- **WHEN** `microjail lock --project /tmp/myproject` is run
- **THEN** the project path used is `/tmp/myproject`

#### Scenario: No --project flag defaults to CWD

- **GIVEN** the current working directory is `/home/user/project`
- **WHEN** `microjail init myproj` is run without `--project`
- **THEN** the project path used is `/home/user/project`

---

### Requirement: Commands use the resolved project path instead of Path.cwd()

All microjail commands SHALL read the project path from the Typer context (`ctx.obj`) rather than calling `Path.cwd()` directly. This decouples command behavior from the process working directory.

#### Scenario: Init writes config at the resolved project path

- **GIVEN** a project at `/tmp/myproject`
- **WHEN** `microjail init myproj --project /tmp/myproject` succeeds through the command layer
- **THEN** `.microjail/config.yaml` is written at `/tmp/myproject/.microjail/config.yaml`

#### Scenario: Lock loads config from the resolved project path

- **GIVEN** a microjail-configured project at `/tmp/myproject`
- **WHEN** `microjail lock --project /tmp/myproject` is run
- **THEN** `MicroJail.load()` is called with `/tmp/myproject` as its argument

#### Scenario: Unlock loads config from the resolved project path

- **GIVEN** a microjail-configured project at `/tmp/myproject`
- **WHEN** `microjail unlock --project /tmp/myproject` is run
- **THEN** `MicroJail.load()` is called with `/tmp/myproject` as its argument

---

### Requirement: --project is forwarded to Workshop subprocess calls

All Workshop subprocess calls in the adapter layer SHALL include the resolved project path via the `--project` flag. This includes `init()`, which currently does not pass `--project`.

#### Scenario: workshop init subprocess receives --project flag

- **GIVEN** the resolved project path is `/tmp/myproject`
- **WHEN** `workshop.init("myproj", project=Path("/tmp/myproject"))` is called
- **THEN** the `workshop init` subprocess command includes `--project /tmp/myproject`

#### Scenario: Other adapter functions already pass --project and remain unchanged

- **GIVEN** the resolved project path is `/tmp/myproject`
- **WHEN** `workshop.launch("myproj", project=Path("/tmp/myproject"))` is called
- **THEN** the `workshop launch` subprocess command includes `--project /tmp/myproject`
