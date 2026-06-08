## 1. Gate Implementation

- [x] 1.1 Create `src/microjail/gates/readonly_config.py` — `ReadonlyConfig(msgspec.Struct)` with `name: str = "readonly-config"` and a `removed: bool` flag to track whether the device was added by this gate
- [x] 1.2 Implement `check(microjail)` — resolve the container via `workshop.get_container`; if the container is `None`, return `False` (gate cannot be enforced without a container); call `lxc.get_instance(container_name, project=lxd_project())`, inspect `expanded_devices` for a device named `"microjail-config-ro"` with `readonly == "true"`; return `True` if found, `False` otherwise
- [x] 1.3 Implement `enforce(microjail)` — resolve the container via `workshop.get_container`; call `lxc.add_device` with `type=disk`, `source=str(microjail.config_path)`, `path="/project/.microjail/config.yaml"`, `readonly=true`; set `removed=True`
- [x] 1.4 Implement `release(microjail)` — if `removed` is `True`, call `lxc.remove_device` for `"microjail-config-ro"` and reset `removed=False`; no-op otherwise

## 2. Integration

- [x] 2.1 Import `ReadonlyConfig` in `src/microjail/lockdown.py` and append it to `Lockdown.default()` gates list (after `NetworkDrop`)
- [x] 2.2 Import `ReadonlyConfig` in `src/microjail/microjail.py` so msgspec's union decoder can resolve the type during `MicroJail.load()`
- [x] 2.3 Export `ReadonlyConfig` from `src/microjail/gates/__init__.py` alongside `Gate`

## 3. Unit Tests

- [x] 3.1 Create `tests/unit/test_readonly_config.py` — define helpers `gate()`, `microjail()`, `patch_container_lookup()`, and `patch_lxc_instance()` mirroring the pattern in `test_network_drop.py`
- [x] 3.2 `test_readonly_config_has_gate_name` — assert `gate().name == "readonly-config"`
- [x] 3.3 `test_check_returns_false_when_device_absent` — mock container lookup and `lxc.get_instance` with no matching device; assert `check()` returns `False`
- [x] 3.4 `test_check_returns_true_when_device_present` — mock container lookup and `lxc.get_instance` with `"microjail-config-ro"` device present and `readonly=true`; assert `check()` returns `True`
- [x] 3.5 `test_enforce_adds_readonly_disk_device` — mock container lookup; call `enforce()`; assert `lxc.add_device` called with device name `"microjail-config-ro"`, `type=disk`, `source=str(microjail.config_path)`, `path="/project/.microjail/config.yaml"`, `readonly=true`
- [x] 3.6 `test_release_removes_device_after_enforce` — enforce then release; assert `lxc.remove_device` called with `"microjail-config-ro"`
- [x] 3.7 `test_release_is_noop_when_not_enforced` — call `release()` without prior `enforce()`; assert `lxc.remove_device` not called
- [x] 3.8 `test_enforce_fails_if_workshop_container_is_not_available` — mock `workshop.get_container` returning `None`; assert `WorkshopNotLaunchedError` raised
- [x] 3.9 `test_check_returns_false_when_container_is_not_available` — mock `workshop.get_container` returning `None`; assert `check()` returns `False` (no raise)

## 4. Update Existing Tests

- [x] 4.1 Update `tests/unit/test_lockdown.py` — `test_default_lockdown_drops_network` becomes two assertions: `NetworkDrop` at index 0, `ReadonlyConfig` at index 1; gate count is 2
- [x] 4.2 Update `tests/unit/test_microjail.py` — `test_load_round_trips_default_network_drop_gate` should also verify the second default gate round-trips as `ReadonlyConfig`

## 5. Functional Tests

- [x] 5.1 Create `tests/functional/gates/test_readonly_config.py` with a module-scoped `launched_workshop` fixture that: creates a temp project dir, calls `workshop.init` + `launch_with_retries`, saves a `MicroJail` config (so `.microjail/config.yaml` exists on disk before the container starts), yields a `SharedWorkshop`, and tears down via `workshop remove`
- [x] 5.2 Add helper `can_write_config(ws: SharedWorkshop) -> bool` — runs `workshop.exec_` with `["bash", "-c", "echo x >> /project/.microjail/config.yaml"]` and returns `True` iff exit code is 0
- [x] 5.3 `test_readonly_config_blocks_write_on_enforce_and_restores_on_release` — skip if baseline write is already denied; build `MicroJail` with `Lockdown(caps=[], gates=[ReadonlyConfig()])`; call `ensure()`; assert `can_write_config()` returns `False`; call `release()`; assert `can_write_config()` returns `True`
