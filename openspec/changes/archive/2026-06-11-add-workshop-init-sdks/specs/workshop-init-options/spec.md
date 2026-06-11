## ADDED Requirements

### Requirement: Init forwards additional SDKs to Workshop

The `microjail init` command SHALL accept zero or more additional Workshop SDK names via a comma-separated `--sdks` flag and pass them through to Workshop initialization alongside microjail's default SDK set (`direnv`). The existing default SDK MUST remain included regardless of whether additional SDKs are requested.

#### Scenario: Init with no --sdks flag delegates to Workshop with default SDKs only

- **GIVEN** a fresh project directory
- **WHEN** `microjail init <name>` is run without a `--sdks` flag
- **THEN** Workshop initialization is invoked with only the default SDK set (`direnv`)

#### Scenario: Init with one SDK forwards it to Workshop

- **GIVEN** a fresh project directory
- **WHEN** `microjail init <name> --sdks golang` is run
- **THEN** Workshop initialization is invoked with the SDK list `["golang", "direnv"]`

#### Scenario: Init with multiple SDKs forwards all to Workshop

- **GIVEN** a fresh project directory
- **WHEN** `microjail init <name> --sdks golang,java` is run
- **THEN** Workshop initialization is invoked with the SDK list `["golang", "java", "direnv"]`

#### Scenario: Init preserves direnv in SDK list even when additional SDKs requested

- **GIVEN** a fresh project directory
- **WHEN** `microjail init <name> --sdks golang` is run
- **THEN** the SDK list passed to Workshop includes `"direnv"` in addition to the requested SDKs

### Requirement: Init forwards base image to Workshop

The `microjail init` command SHALL accept an optional `--base` flag and pass it through to Workshop initialization. When `--base` is not provided, the flag MUST be omitted from the Workshop subprocess call, allowing Workshop to apply its own default.

#### Scenario: Init with --base forwards it to Workshop

- **GIVEN** a fresh project directory
- **WHEN** `microjail init <name> --base ubuntu@22.04` is run
- **THEN** Workshop initialization is invoked with `--base ubuntu@22.04`

#### Scenario: Init without --base omits the flag

- **GIVEN** a fresh project directory
- **WHEN** `microjail init <name>` is run without a `--base` flag
- **THEN** the `--base` flag is absent from the Workshop subprocess call

### Requirement: Init handles Workshop SDK or base failures without writing config

When Workshop initialization fails for any reason (including invalid or unavailable SDK names or base images), the `microjail init` command SHALL exit non-zero and SHALL NOT write `.microjail/config.yaml`.

#### Scenario: Init exits non-zero on Workshop SDK failure

- **GIVEN** a fresh project directory
- **WHEN** `microjail init <name> --sdks invalid-sdk-name` is run and Workshop rejects the SDK
- **THEN** the command exits with a non-zero code, reports a user-facing error, and does not write `.microjail/config.yaml`

### Requirement: Adopt ignores additional init flags

The `microjail init --adopt` command SHALL silently ignore `--sdks` and SHALL warn when `--base` is passed, since adoption attaches microjail to an existing Workshop without re-initializing it.

#### Scenario: Adopt with --sdks flag succeeds and ignores the SDKs

- **GIVEN** an existing Workshop project
- **WHEN** `microjail init <name> --adopt --sdks golang` is run
- **THEN** the command succeeds, writes `.microjail/config.yaml` bound to the existing Workshop, and does not modify the Workshop's SDK list

#### Scenario: Adopt with --base warns and succeeds

- **GIVEN** an existing Workshop project
- **WHEN** `microjail init <name> --adopt --base ubuntu@22.04` is run
- **THEN** the command emits a warning that `--base` has no effect during adopt, succeeds, and writes `.microjail/config.yaml` bound to the existing Workshop

### Requirement: Overwrite forwards SDKs and base through re-initialization

The `microjail init --overwrite` command SHALL forward `--sdks` and `--base` flags to the new Workshop initialization that follows the overwrite.

#### Scenario: Overwrite with --sdks and --base re-initializes with the requested options

- **GIVEN** a project with an existing Workshop
- **WHEN** `microjail init <name> --overwrite --sdks golang --base ubuntu@22.04` is run
- **THEN** the existing Workshop YAML is removed, Workshop initialization is invoked with `["golang", "direnv"]` and `--base ubuntu@22.04`, and `.microjail/config.yaml` is written
