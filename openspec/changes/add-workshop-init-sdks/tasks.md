## Slice 1: Init command default behavior preserved (tracer bullet)

- [ ] 1.1 RED: `test_init_delegates_to_workshop_with_default_sdks`, `test_init_default_omits_base`
- [ ] 1.2 GREEN: Add `sdks: list[str] | None = None` and `base: str | None = None` parameters to `commands/init.py:init()`. Forward `sdks` and `base` to `workshop.init(name, sdks=sdks, base=base)`. Pass `project=Path.cwd()` to `workshop.init()` (prepare for --project in later slice). No CLI flag wiring yet — tests call through `CliRunner` asserting default behavior still works with the new signature. Update adapter signature: `workshop.init(name, project, sdks=None, base=None)`. Add `--project` flag to subprocess call when `project` is provided.
- [ ] 1.3 REFACTOR: update `save_microjail_config(name)` to accept `project: Path` parameter instead of hardcoding `Path.cwd()`. Update callers in `init()`, `overwrite_workshop()`, `adopt_workshop()`.

## Slice 2: --sdks CLI forwarding

- [ ] 2.1 RED: `test_init_forwards_single_sdk`, `test_init_forwards_multiple_sdks`, `test_init_preserves_direnv_in_sdk_list`, `test_init_forwards_sdks_to_adapter`
- [ ] 2.2 GREEN: Wire `--sdks` CLI option in `cli.py` (Typer `Annotated[str, typer.Option(help="...")]`). In `init()`, split comma-separated `--sdks` value into `list[str]` and pass to `workshop.init()`. Adapter appends `"direnv"` to the list.
- [ ] 2.3 REFACTOR: none

## Slice 3: --base CLI forwarding

- [ ] 3.1 RED: `test_init_forwards_base`, `test_init_forwards_base_to_adapter`, `test_init_omits_base_when_not_provided`
- [ ] 3.2 GREEN: Wire `--base` CLI option in `cli.py` (`typer.Option`). Pass `base` value through `init()` to `workshop.init()`. Adapter conditionally includes `--base` in subprocess call when not `None`.
- [ ] 3.3 REFACTOR: none

## Slice 4: Failure handling and adopt behavior

- [ ] 4.1 RED: `test_init_exits_nonzero_on_sdk_failure`, `test_adopt_ignores_sdks`, `test_adopt_warns_on_base`
- [ ] 4.2 GREEN: Existing failure handling in `init()` already catches `Exception` and exits non-zero without writing config — verify this covers SDK/base failures. Add adopt-warn logic: when `--adopt --base <value>` is passed, emit `typer.echo("... --base is ignored during adopt", err=True)` before calling `adopt_workshop()`. `--sdks` is already silently ignored because `adopt_workshop()` never calls `workshop.init()`.
- [ ] 4.3 REFACTOR: none

## Slice 5: --overwrite forwarding

- [ ] 5.1 RED: `test_overwrite_forwards_sdks_and_base`
- [ ] 5.2 GREEN: Update `overwrite_workshop(name, sdks=None, base=None)` to accept and forward `sdks` and `base` to `init(name, sdks=sdks, base=base)`. Wire CLI so `--overwrite` path receives the same `--sdks`/`--base` values as fresh init.
- [ ] 5.3 REFACTOR: none

## Slice 6: --project flag resolution

- [ ] 6.1 RED: `test_project_flag_resolves_relative_to_absolute`, `test_project_flag_accepts_absolute_path`, `test_project_flag_defaults_to_cwd`
- [ ] 6.2 GREEN: Add `@app.callback()` to `cli.py` defining global `--project` / `-p` option. Resolve to `Path(project).resolve()` if provided, else `Path.cwd()`. Store in `ctx.obj`. Update all command functions to accept `ctx: typer.Context` as first parameter.
- [ ] 6.3 REFACTOR: none

## Slice 7: Commands use resolved project path

- [ ] 7.1 RED: `test_init_writes_config_at_resolved_project_path`, `test_lock_loads_config_from_resolved_project_path`, `test_unlock_loads_config_from_resolved_project_path`
- [ ] 7.2 GREEN: Replace `Path.cwd()` with `ctx.obj` in all commands: `init.py` (`save_microjail_config`, `overwrite_workshop`, `adopt_workshop`, `workshop.init` call), `lock.py` (`load_microjail_or_exit`), `unlock.py` (`MicroJail.load`), `run.py` (via `load_microjail_or_exit`). Update `workshop.init()` to accept and forward `--project` in subprocess call. Update `WorkshopExistsError.project` to use the resolved path.
- [ ] 7.3 REFACTOR: extract `ctx.obj` access into `get_project(ctx: typer.Context) -> Path` helper to avoid repeated `typer.Context` annotation noise.

## Slice 8: --project forwarded to Workshop subprocesses

- [ ] 8.1 RED: `test_workshop_init_subprocess_receives_project_flag`, `test_workshop_launch_subprocess_receives_project_flag`
- [ ] 8.2 GREEN: Verify `workshop.init()` subprocess call includes `"--project", str(project)`. Existing adapter functions (`launch`, `info`, `exec_`, etc.) already pass `--project` — confirm with test. Add `--project` to `workshop.init()` subprocess and `workshop.exists()` if it doesn't already.
- [ ] 8.3 REFACTOR: none

## Slice 9: README update

- [ ] 9.1 Update README init usage section with `--sdks`, `--base`, and `--project` examples.
