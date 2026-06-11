## Tracer Bullet

- **Test**: `tests/e2e/test_destroy_e2e.py::test_destroy_default_behavior`
- **Capability**: Default destroy preserves project definitions
- **Green**: Initializing a microjail and running destroy removes the workshop container (verified via `lxc info` failing) and removes `data/`, but `.microjail/config.yaml` still exists on disk.

## Test Plan

### Slice 1: Safe State Resolution

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| Destroying a Pending workshop | `test_destroy_pending_workshop` | Init project, mock `workshop.info` to return "Pending" then "Ready". | `microjail destroy` CLI call. | Command polls `info()` multiple times before calling `workshop.remove()`. |
| Destroying an Off workshop | `test_destroy_off_workshop` | Init project, mock `workshop.info` to return "Off". | `microjail destroy` CLI call. | `workshop.start()` is called before `workshop.remove()`. |

### Slice 2: Destroy Command Scenarios

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| Default destroy preserves project definitions | `test_destroy_default_behavior` | Init project, start workshop. Create a file inside `data/`. | `microjail destroy` CLI call. | `workshop.exists()` is False. `(project_path / "data")` does not exist. `(project_path / ".microjail/config.yaml")` exists. |
| Total project teardown requires confirmation | `test_destroy_all_interactive` | Init project. Mock stdin to simulate user typing "y". | `microjail destroy --all` CLI call. | `typer.confirm` was called. Project directory does not exist. |
| Bypassing confirmation for total teardown | `test_destroy_all_bypass` | Init project. | `microjail destroy --all --yes-i-really-mean-it` CLI call. | No prompt shown. Project directory does not exist. |
| Infrastructure teardown failure | `test_destroy_infrastructure_failure` | Init project, mock `workshop.remove` to raise an exception. | `microjail destroy` CLI call. | `typer.Exit` raised with exit code 1. `project_path / "data"` still exists. |

### Slice 3: Init Command Scenarios

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| Initializing a project creates the data directory | `test_init_creates_purge_path` | Temporary empty directory. | `microjail init test-jail` CLI call. | `.microjail/config.yaml` exists and `MicroJail.load().purge_path == "data"`. `data/` directory exists in project root. |
