## Tracer Bullet

- **Test**: `tests/functional/commands/test_init.py::test_init_delegates_to_workshop_with_default_sdks`
- **Capability**: `workshop-init-options` — Init forwards additional SDKs to Workshop (default case)
- **Green**: `workshop.init` called with `sdks=["direnv"]` (no user flags passed), config written

## Test Plan

### Slice 1: Init command default behavior preserved

Proves the new parameterized init signature still works for the zero-flag case.

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| Init with no --sdks flag delegates to Workshop with default SDKs only | `test_init_delegates_to_workshop_with_default_sdks` | `patch("microjail.adapters.workshop.init")`; `monkeypatch.chdir(tmp_path)` | `CliRunner().invoke(app, ["init", project_name])` | `mock_init.assert_called_once_with(project_name)`; config written; defaults: `sdks` not passed or `sdks=["direnv"]` |
| Init without --base omits the flag | `test_init_default_omits_base` | Same as above | `CliRunner().invoke(app, ["init", project_name])` | `mock_init` not called with `base` kwarg, or `base=None` |

### Slice 2: --sdks forwarding

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| Init with one SDK forwards it to Workshop | `test_init_forwards_single_sdk` | `patch("microjail.adapters.workshop.init")`; `monkeypatch.chdir(tmp_path)` | `CliRunner().invoke(app, ["init", project_name, "--sdks", "golang"])` | `mock_init.assert_called_once_with(project_name, sdks=["golang"])` |
| Init with multiple SDKs forwards all to Workshop | `test_init_forwards_multiple_sdks` | Same as above | `CliRunner().invoke(app, ["init", project_name, "--sdks", "golang,java"])` | `mock_init.assert_called_once_with(project_name, sdks=["golang", "java"])` |
| Init preserves direnv in SDK list | `test_init_preserves_direnv_in_sdk_list` | Same as above | `CliRunner().invoke(app, ["init", project_name, "--sdks", "golang"])` | `mock_init` called; the `sdks` list contains `"direnv"` (adapter responsibility — verify command passes list, adapter adds `direnv`) |
| Init forwards --sdks flag to Workshop adapter (delta) | `test_init_forwards_sdks_to_adapter` | Same as above | `CliRunner().invoke(app, ["init", project_name, "--sdks", "golang"])` | `mock_init` called with `sdks` list that includes both `"golang"` and `"direnv"` |

### Slice 3: --base forwarding

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| Init with --base forwards it to Workshop | `test_init_forwards_base` | `patch("microjail.adapters.workshop.init")`; `monkeypatch.chdir(tmp_path)` | `CliRunner().invoke(app, ["init", project_name, "--base", "ubuntu@22.04"])` | `mock_init.assert_called_once_with(project_name, base="ubuntu@22.04")` |
| Init forwards --base flag to Workshop adapter (delta) | `test_init_forwards_base_to_adapter` | Same as above | `CliRunner().invoke(app, ["init", project_name, "--base", "ubuntu@22.04"])` | `mock_init` called with `base="ubuntu@22.04"` |
| Init with no --base omits the flag from the adapter call (delta) | `test_init_omits_base_when_not_provided` | Same as above | `CliRunner().invoke(app, ["init", project_name])` | `mock_init` called with `base=None` or no `base` kwarg |

### Slice 4: Failure handling and adopt behavior

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| Init exits non-zero on Workshop SDK failure | `test_init_exits_nonzero_on_sdk_failure` | `patch("microjail.adapters.workshop.init", side_effect=RuntimeError("invalid SDK"))`; `monkeypatch.chdir(tmp_path)` | `CliRunner().invoke(app, ["init", project_name, "--sdks", "invalid-sdk-name"])` | `result.exit_code != 0`; `"Failed to initialize Workshop"` in stderr; no `.microjail/config.yaml` written |
| Adopt with --sdks flag succeeds and ignores the SDKs | `test_adopt_ignores_sdks` | `patch("microjail.adapters.workshop.exists", return_value=True)`; `monkeypatch.chdir(tmp_path)` | `CliRunner().invoke(app, ["init", project_name, "--adopt", "--sdks", "golang"])` | `result.exit_code == 0`; config written; `workshop.init` NOT called |
| Adopt with --base warns and succeeds | `test_adopt_warns_on_base` | `patch("microjail.adapters.workshop.exists", return_value=True)`; `monkeypatch.chdir(tmp_path)` | `CliRunner().invoke(app, ["init", project_name, "--adopt", "--base", "ubuntu@22.04"])` | `result.exit_code == 0`; stderr contains warning about `--base` ignored; config written; `workshop.init` NOT called |

### Slice 5: --overwrite forwarding

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| Overwrite with --sdks and --base re-initializes with the requested options | `test_overwrite_forwards_sdks_and_base` | `patch("microjail.adapters.workshop.init")`; create `.workshop/<name>.yaml` file; `monkeypatch.chdir(tmp_path)` | `CliRunner().invoke(app, ["init", project_name, "--overwrite", "--sdks", "golang", "--base", "ubuntu@22.04"])` | `mock_init.assert_called_once_with(project_name, sdks=["golang"], base="ubuntu@22.04")`; config written |

### Slice 6: --project flag resolution

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| --project flag resolves relative path to absolute | `test_project_flag_resolves_relative_to_absolute` | `monkeypatch.chdir("/tmp")`; `patch("microjail.adapters.workshop.init")` | `CliRunner().invoke(app, ["init", project_name, "--project", "../other"])` | `ctx.obj` = `Path("/other").resolve()`; command operates on that path |
| --project flag accepts absolute path unchanged | `test_project_flag_accepts_absolute_path` | create project at `/tmp/myproject`; `patch("microjail.adapters.workshop.init")` | `CliRunner().invoke(app, ["init", project_name, "--project", "/tmp/myproject"])` | `ctx.obj` = `Path("/tmp/myproject")`; config written there |
| No --project flag defaults to CWD | `test_project_flag_defaults_to_cwd` | `monkeypatch.chdir(tmp_path)`; `patch("microjail.adapters.workshop.init")` | `CliRunner().invoke(app, ["init", project_name])` | `ctx.obj` = `Path(tmp_path)`; config written at cwd |

### Slice 7: Commands use resolved project path

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| Init writes config at the resolved project path | `test_init_writes_config_at_resolved_project_path` | create directory `/tmp/myproject`; `patch("microjail.adapters.workshop.init")` | `CliRunner().invoke(app, ["init", project_name, "--project", "/tmp/myproject"])` | `.microjail/config.yaml` exists at `/tmp/myproject/.microjail/config.yaml` |
| Lock loads config from the resolved project path | `test_lock_loads_config_from_resolved_project_path` | write config at `/tmp/myproject/.microjail/config.yaml` with valid Lockdown; `patch("microjail.microjail.MicroJail.ensure")` | `CliRunner().invoke(app, ["lock", "--project", "/tmp/myproject"])` | `MicroJail.load(Path("/tmp/myproject"))` was called; `ensure` called on the loaded instance |
| Unlock loads config from the resolved project path | `test_unlock_loads_config_from_resolved_project_path` | write config at `/tmp/myproject/.microjail/config.yaml` with valid Lockdown; `patch("microjail.microjail.MicroJail.release")` | `CliRunner().invoke(app, ["unlock", "--project", "/tmp/myproject"])` | `MicroJail.load(Path("/tmp/myproject"))` was called; `release` called on the loaded instance |

### Slice 8: --project forwarded to Workshop subprocesses

| Scenario | Test | Arrange | Act | Assert |
|----------|------|---------|-----|--------|
| workshop init subprocess receives --project flag | `test_workshop_init_subprocess_receives_project_flag` | `patch("subprocess.run")` as `mock_run` | `workshop.init("myproj", project=Path("/tmp/myproject"))` | `mock_run` called with arg list containing `"--project"` and `"/tmp/myproject"` |
| Other adapter functions already pass --project and remain unchanged | `test_workshop_launch_subprocess_receives_project_flag` | `patch("subprocess.run")` as `mock_run` | `workshop.launch("myproj", project=Path("/tmp/myproject"))` | `mock_run` called with arg list containing `"--project"` and `"/tmp/myproject"` |
