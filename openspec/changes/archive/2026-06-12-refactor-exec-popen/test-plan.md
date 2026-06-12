## Tracer Bullet

- **Test**: `tests/functional/adapters/test_workshop.py::test_popen_executes_command_in_background`
- **Capability**: `workshop-popen / Scenario: Executing a command in background`
- **Green**: The test successfully calls `workshop.popen` for a running workshop and immediately returns a `subprocess.Popen` object while the command runs in the background.

## Test Plan

### Slice 1: Basic popen functionality and background execution

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| Executing a command in background | `test_popen_executes_command_in_background` | A launched workshop instance `launched_workshop`. | Call `workshop.popen(launched_workshop.name, launched_workshop.path, ["sleep", "10"])` | Returned value is an instance of `subprocess.Popen`, the process poll state is initially `None` (running), and terminates cleanly. |
| Non-blocking execution via MicroJail wrapper | `test_microjail_popen_executes_command_in_background` | A running workshop and a initialized `MicroJail` object. | Call `mj.popen(["sleep", "10"])` | Returned value is an instance of `subprocess.Popen`, is active, and can be terminated. |
| Interactive PTY command execution | `test_popen_interactive_direct_inheritance` | A launched workshop instance `launched_workshop`. | Call `workshop.popen(..., ["sh"], interactive=True)` | The process starts, uses interactive mode, and can be terminated. |

### Slice 2: Standard streams interaction

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| Interacting with standard streams | `test_popen_interacts_with_standard_streams` | A launched workshop instance `launched_workshop`. | Call `workshop.popen(..., ["cat"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)` | Write to stdin, read from stdout, and assert correct values are exchanged. |

### Slice 3: Exception and error cases

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| Target workshop does not exist | `test_popen_fails_if_workshop_does_not_exist` | A temporary/non-existent workshop path/name. | Call `workshop.popen("fake", path, ["true"])` | Raises `workshop.WorkshopNotFoundError`. |
| Target workshop exists but is not launched | `test_popen_fails_if_workshop_is_not_launched` | An initialized but unlaunched workshop instance `initialized_workshop`. | Call `workshop.popen(initialized_workshop.name, initialized_workshop.path, ["true"])` | Raises `workshop.WorkshopNotLaunchedError`. |
