## Slice 1: Initializing a project creates the data directory

- [x] 1.1 RED: `test_init_creates_purge_path`
- [x] 1.2 GREEN: Add `MicroJail.purge_path` field, update `init` command to read `purge_path` from config and `mkdir()` it on the filesystem.
- [x] 1.3 REFACTOR: none

## Slice 2: Safe State Resolution (Pending / Off)
- [x] 2.1 RED: `test_destroy_pending_workshop` and `test_destroy_off_workshop`
- [x] 2.2 GREEN: In `adapters/workshop.py` (or CLI), add wait/poll logic if status is `Pending`, and run `workshop start` if status is `Off` before teardown.
- [x] 2.3 REFACTOR: Extract polling logic into a small helper.

## Slice 3: Default destroy preserves project definitions (Tracer Bullet)

- [x] 3.1 RED: `test_destroy_default_behavior`
- [x] 3.2 GREEN: Implement `destroy` in `src/microjail/cli.py`, call `workshop.remove`, and then `shutil.rmtree` on the `purge_path`.
- [x] 3.3 REFACTOR: none

## Slice 4: Total project teardown and confirmation

- [x] 4.1 RED: `test_destroy_all_interactive` and `test_destroy_all_bypass`
- [x] 4.2 GREEN: Add `--all` and `--yes-i-really-mean-it` flags. Use `typer.confirm()` when `--all` is used without bypass. Remove `project_path` recursively if confirmed.
- [x] 4.3 REFACTOR: none
## Slice 5: Infrastructure teardown failure

- [x] 5.1 RED: `test_destroy_infrastructure_failure`
- [x] 5.2 GREEN: Ensure exceptions from `workshop.remove` or state resolution are caught/propagated before any `shutil.rmtree` is called on the local filesystem.
- [x] 5.3 REFACTOR: none
