## ADDED Requirements

### Requirement: Interactive shell command applies Lockdown before starting shell

The system SHALL provide a `microjail shell` command that applies the configured Lockdown before starting an interactive shell workload.

#### Scenario: Shell starts after successful policy application
- **GIVEN** a configured Microjail project with a launchable Workshop
- **AND** all declared Capabilities and Gates can be applied
- **WHEN** the user invokes `microjail shell`
- **THEN** Microjail launches the Workshop if needed
- **AND** applies the configured Lockdown
- **AND** starts the shell only after Lockdown application succeeds.

#### Scenario: Capability failure blocks shell start
- **GIVEN** a configured Microjail project with a declared Capability that cannot be applied
- **WHEN** the user invokes `microjail shell`
- **THEN** Microjail reports the Capability application failure
- **AND** does not start the shell workload.

#### Scenario: Gate failure blocks shell start
- **GIVEN** a configured Microjail project with a Gate that cannot be enforced
- **WHEN** the user invokes `microjail shell`
- **THEN** Microjail reports the Gate application failure
- **AND** does not start the shell workload.

### Requirement: Interactive shell command uses PTY-backed Workshop execution

The system SHALL start the shell workload through Workshop interactive execution so the workload inherits the host terminal PTY.

#### Scenario: Default shell uses interactive execution
- **GIVEN** a configured Microjail project whose Lockdown applies successfully
- **WHEN** the user invokes `microjail shell`
- **THEN** Microjail starts the container's default shell with interactive Workshop execution enabled.

#### Scenario: Explicit shell command uses interactive execution
- **GIVEN** a configured Microjail project whose Lockdown applies successfully
- **WHEN** the user invokes `microjail shell -- bash -l`
- **THEN** Microjail starts `bash -l` with interactive Workshop execution enabled.

#### Scenario: Non-TTY invocation is rejected before policy application
- **GIVEN** stdin or stdout is not attached to a terminal
- **WHEN** the user invokes `microjail shell`
- **THEN** Microjail exits with an operator-facing error
- **AND** does not apply Lockdown
- **AND** does not start a shell workload.

### Requirement: Interactive shell command is supervised like run

While the interactive shell workload is running, the system SHALL supervise runtime policy through the Warden and SHALL preserve the shell process exit code when no runtime policy violation occurs.

#### Scenario: Shell exit code is preserved
- **GIVEN** a configured Microjail project whose Lockdown applies successfully
- **AND** the shell workload exits with code 7
- **WHEN** the user invokes `microjail shell -- sh -c 'exit 7'`
- **THEN** Microjail exits with code 7.

#### Scenario: Gate policy violation is fatal
- **GIVEN** a configured Microjail project whose Lockdown applies successfully
- **AND** the Warden detects a Gate policy violation while the shell workload is running
- **WHEN** the user invokes `microjail shell`
- **THEN** Microjail terminates the workload using the Warden policy violation path
- **AND** exits with the runtime Gate policy violation code.

#### Scenario: Fatal Capability policy violation is fatal
- **GIVEN** a configured Microjail project whose Lockdown applies successfully
- **AND** the Warden detects a fatal Capability policy violation while the shell workload is running
- **WHEN** the user invokes `microjail shell`
- **THEN** Microjail terminates the workload using the Warden policy violation path
- **AND** exits with the fatal runtime Capability policy violation code.

### Requirement: Interactive shell command does not change run semantics

The system SHALL keep `microjail run` non-interactive and SHALL NOT auto-unlock policy after `microjail shell` exits.

#### Scenario: Run remains non-interactive
- **GIVEN** a configured Microjail project whose Lockdown applies successfully
- **WHEN** the user invokes `microjail run -- bash`
- **THEN** Microjail starts the workload with non-interactive Workshop execution.

#### Scenario: Shell exit leaves Lockdown applied
- **GIVEN** a configured Microjail project whose Lockdown applies successfully
- **WHEN** an interactive shell started by `microjail shell` exits normally
- **THEN** Microjail does not automatically release Gates or revoke Capabilities.
