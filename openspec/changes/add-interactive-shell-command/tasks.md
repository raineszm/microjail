# Implementation Tasks

## Slice 1: Tracer Bullet - Interactive Shell Starts After Policy
- **Test**: `test_shell_applies_lockdown_then_starts_default_shell_interactively` in `tests/functional/commands/test_shell.py`
- **Arrange**: Create a temporary project with a documented Microjail config, monkeypatch `MicroJail.load`/command loading to return a `MicroJail` whose `workshop_info()` reports launched, monkeypatch shell TTY checks to return true, monkeypatch `ensure_lockdown` to record policy application, monkeypatch `MicroJail.shell` to return a mock process, and monkeypatch `Warden.supervise` to return `0`.
- **Act**: Invoke `CliRunner().invoke(app, ["shell"])`.
- **Assert**: Exit code is `0`, policy application was called before `MicroJail.shell`, `MicroJail.shell` was called once, and `Warden.supervise` received the shell process.

- [x] 1.1 RED: Add `test_shell_applies_lockdown_then_starts_default_shell_interactively`
- [x] 1.2 GREEN: Add `microjail shell` command registration and minimal implementation using `MicroJail.shell()` after Lockdown succeeds
- [x] 1.3 REFACTOR: Extract shared run/shell supervision helper only if the duplicate exception/finally handling is material after Slice 1

## Slice 2: Explicit Shell Command Override
- **Test**: `test_shell_uses_explicit_command_interactively` in `tests/functional/commands/test_shell.py`
- **Arrange**: Reuse the shell command fixture seams from Slice 1 with TTY checks returning true, successful Lockdown, a mock process from `MicroJail.popen`, and `Warden.supervise` returning `0`.
- **Act**: Invoke `CliRunner().invoke(app, ["shell", "--", "bash", "-l"])`.
- **Assert**: Exit code is `0` and `MicroJail.popen` is called once with `["bash", "-l"]` and `interactive=True`.

- [x] 2.1 RED: Add `test_shell_uses_explicit_command_interactively`
- [x] 2.2 GREEN: Parse optional shell command override and pass it to `MicroJail.popen(..., interactive=True)`
- [x] 2.3 REFACTOR: Keep shell test setup readable without broad fixtures unless a second test exposes real duplication

## Slice 3: Policy Failures Block Shell Start
- **Tests**: `test_shell_capability_failure_blocks_workload_and_skips_gates` and `test_shell_gate_failure_blocks_workload` in `tests/functional/commands/test_shell.py`
- **Arrange**: Create MicroJail instances with failing `RecordingCapability` or failing `RecordingGate`, allow TTY checks, and monkeypatch `MicroJail.popen`.
- **Act**: Invoke `CliRunner().invoke(app, ["shell"])`.
- **Assert**: Capability failure exits with `policy.CAPABILITY_APPLICATION_FAILURE`, gate failure exits with `policy.GATE_APPLICATION_FAILURE`, failure names appear on stderr, and `MicroJail.popen` is not called.

- [x] 3.1 RED: Add shell Capability and Gate failure tests
- [x] 3.2 GREEN: Ensure shell uses the same pre-workload Lockdown failure path as run
- [x] 3.3 REFACTOR: Share shell test setup only where it clarifies policy failure coverage

## Slice 4: Runtime Policy Violations Mirror Run
- **Tests**: `test_shell_propagates_workload_exit_status`, `test_shell_exits_with_84_on_gate_violation`, and `test_shell_exits_with_82_on_fatal_capability_violation` in `tests/functional/commands/test_shell.py`
- **Arrange**: Allow TTY checks, configure an already-launched MicroJail, monkeypatch `MicroJail.popen` to return a mock process, and monkeypatch `Warden.supervise` to return `7` or raise the matching runtime policy exception.
- **Act**: Invoke `CliRunner().invoke(app, ["shell", "--", "sh", "-c", "exit 7"])` for exit preservation and `CliRunner().invoke(app, ["shell"])` for runtime violations.
- **Assert**: Normal shell workload exit code is preserved, runtime Gate violation exits with `policy.RUNTIME_GATE_POLICY_VIOLATION`, and fatal runtime Capability violation exits with `policy.FATAL_RUNTIME_CAPABILITY_VIOLATION`.

- [x] 4.1 RED: Add shell exit-code and runtime policy violation tests
- [x] 4.2 GREEN: Route shell supervision through the shared Warden policy violation exit mapping
- [x] 4.3 REFACTOR: Keep run and shell supervision behavior centralized in `supervise_workload`

## Slice 5: Non-TTY Invocation Is Rejected Early
- **Test**: `test_shell_rejects_non_tty_before_loading_policy` in `tests/functional/commands/test_shell.py`
- **Arrange**: Parameterize stdin/stdout TTY checks so either stream can be non-TTY, monkeypatch `MicroJail.load`, shell `ensure_lockdown`, and `MicroJail.popen` with mocks.
- **Act**: Invoke `CliRunner().invoke(app, ["shell"])`.
- **Assert**: Exit code is non-zero, stderr names the interactive terminal requirement, and Microjail loading, Lockdown application, and shell workload start are not called.

- [x] 5.1 RED: Add non-TTY rejection test for stdin and stdout
- [x] 5.2 GREEN: Reject non-TTY shell invocation before project loading or policy application
- [x] 5.3 REFACTOR: Keep TTY checks as small monkeypatchable boundary functions

## Slice 6: Run Remains Non-Interactive
- **Test**: `test_run_remains_non_interactive_after_shell_addition` in `tests/functional/commands/test_run.py`
- **Arrange**: Configure an already-launched MicroJail, monkeypatch `MicroJail.popen`, and monkeypatch `Warden.supervise` to return `0`.
- **Act**: Invoke `CliRunner().invoke(app, ["run", "--", "bash"])`.
- **Assert**: `MicroJail.popen` is called once with `["bash"]` and `interactive=False`.

- [x] 6.1 RED: Add run regression test proving shell does not alter run interactivity
- [x] 6.2 GREEN: Keep `run` wired to `MicroJail.popen(..., interactive=False)`
- [x] 6.3 REFACTOR: Avoid merging run and shell argument parsing

## Slice 7: Documentation And Focused Verification
- **Docs**: Update `README.md` usage to document `microjail shell`, the `bash` default, explicit `--` command override, interactive terminal requirement, and no automatic unlock.
- **Verification**: Run focused command tests for shell/run behavior and run lint/type hooks for changed files through `prek run`.
- **Assert**: Documentation matches implemented behavior; shell tests and existing run tests pass; hooks pass.

- [x] 7.1 RED: Identify README usage section that documents run/lock workflow
- [x] 7.2 GREEN: Document `microjail shell` behavior and examples
- [x] 7.3 REFACTOR: Run focused tests and project hooks, then fix issues
