# workshop-popen Specification

## Purpose
TBD - created by archiving change refactor-exec-popen. Update Purpose after archive.
## Requirements
### Requirement: Non-blocking Workload execution

The system SHALL support launching the Workload asynchronously inside the Workshop environment, returning a Workload process handle that represents the executing Workload and permits non-blocking operations.

#### Scenario: Executing a command in background
- **GIVEN** a launched Workshop environment
- **WHEN** executing a command asynchronously
- **THEN** a Workload process handle is returned immediately while the Workload runs in the background.

#### Scenario: Interacting with standard streams
- **GIVEN** a launched Workshop environment
- **WHEN** executing a command that reads stdin and writes stdout asynchronously
- **THEN** stdin/stdout streams of the Workload process handle can be accessed and read/written by the caller.

#### Scenario: Interactive PTY command execution
- **GIVEN** a launched Workshop environment
- **WHEN** executing a command asynchronously with interactive mode enabled and standard streams inheriting the host terminal
- **THEN** the Workload connects to the host terminal PTY directly and allows user interaction.

### Requirement: Error handling for non-existent or unlaunched Workshop environments

The system SHALL raise a workshop not found error if the target Workshop environment does not exist, and a workshop not launched error if the Workshop environment exists but has not been launched yet, when attempting asynchronous execution.

#### Scenario: Target Workshop environment does not exist
- **GIVEN** a Workshop name that does not exist on disk
- **WHEN** attempting to execute a command asynchronously
- **THEN** a workshop not found exception is raised.

#### Scenario: Target Workshop environment exists but is not launched
- **GIVEN** a Workshop name that exists but whose environment is not currently launched/running
- **WHEN** attempting to execute a command asynchronously
- **THEN** a workshop not launched exception is raised.
