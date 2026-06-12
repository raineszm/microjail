## Tracer Bullet

- **Test**: `tests/functional/commands/test_run.py::test_run_launches_workshop_if_not_launched`
- **Capability**: `user-facing-test-coverage` / `Run auto-launches workshop if not launched`
- **Green**: The test passes when `microjail run` automatically invokes `workshop.launch` after detecting that the workshop is not launched.

## Test Plan

### Slice 1: Functional check of auto-launch behavior

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| Run auto-launches workshop if not launched | `test_run_launches_workshop_if_not_launched` | Construct `MicroJail` config; mock `MicroJail.load`; mock `MicroJail.workshop_info` to return `None`; mock `workshop.launch`; mock workload execution (`ensure_lockdown`, `popen`, `Warden`) | Invoke CLI `microjail run -- true` | `workshop_info` is queried; `workshop.launch` is called with correct arguments; command proceeds without error |

### Slice 2: E2E check of auto-launch behavior

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| Run auto-launches workshop if not launched | `test_run_auto_launches_workshop_e2e` | Initialize fresh project; do NOT launch workshop container | Invoke CLI `microjail run -- true` | Command exits 0; workshop info is now queryable and status is `ready` |
