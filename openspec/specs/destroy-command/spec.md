## Purpose

The `destroy-command` capability enables complete teardown of a microjail environment, ensuring that heavy infrastructure (containers, snapshots) is deleted before local filesystem cleanup.

---

## Requirements

### Requirement: Unified Destroy Lifecycle
The system must provide a command to tear down a microjail environment, ensuring that heavy infrastructure (containers, snapshots) is deleted before proceeding to local filesystem cleanup.

#### Scenario: Default destroy preserves project definitions
- **GIVEN** an active microjail project with a configured `purge_path` (defaulting to `data`)
- **WHEN** the user executes `microjail destroy`
- **THEN** the underlying workshop and its containers are stopped and removed
- **AND** any snapshots or caches associated with this specific instance are purged
- **AND** the local directory specified by `purge_path` is recursively deleted
- **AND** the rest of the project (e.g., `.microjail/`, `.workshop/`) remains intact

#### Scenario: Infrastructure teardown failure
- **GIVEN** an active microjail project
- **WHEN** the infrastructure teardown phase fails (e.g., workshop CLI errors)
- **THEN** no local directories are deleted
- **AND** the command exits with an error

---

### Requirement: Safe State Resolution Before Removal
The command must gracefully handle intermediate workshop states before attempting removal.

#### Scenario: Destroying a Pending workshop
- **GIVEN** a microjail project where the workshop status is "Pending"
- **WHEN** the user executes `microjail destroy`
- **THEN** the command polls until the status is no longer "Pending" (or times out)
- **AND** once stable, proceeds with removal

#### Scenario: Destroying an Off workshop
- **GIVEN** a microjail project where the workshop status is "Off"
- **WHEN** the user executes `microjail destroy`
- **THEN** the command executes `workshop start` to bring it online
- **AND** proceeds with removal

---

### Requirement: Total Teardown and Confirmation
The user can opt to destroy the entire project, but must be protected from accidental deletion.

#### Scenario: Total project teardown requires confirmation
- **GIVEN** an active microjail project
- **WHEN** the user executes `microjail destroy --all`
- **THEN** an interactive prompt asks for confirmation
- **AND** if confirmed, the infrastructure is removed and the entire project directory is recursively deleted

#### Scenario: Bypassing confirmation for total teardown
- **GIVEN** an active microjail project
- **WHEN** the user executes `microjail destroy --all --yes-i-really-mean-it`
- **THEN** no interactive prompt is shown
- **AND** the infrastructure and entire project directory are recursively deleted

---

### Requirement: Automatic Purge Path Creation
To encourage users to isolate sensitive data, the `purge_path` directory must be created automatically when the project is initialized.

#### Scenario: Initializing a project creates the data directory
- **GIVEN** a directory targeted for microjail initialization
- **WHEN** the user executes `microjail init`
- **THEN** the microjail configuration is created with `purge_path` defaulting to `data`
- **AND** a `data/` directory is created on the local filesystem within the project
