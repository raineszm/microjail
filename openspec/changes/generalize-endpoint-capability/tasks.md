## 1. Struct Fields and resolved_endpoint

- [x] 1.1 TEST: Add test in `test_endpoint_capability.py` for `resolved_endpoint` returning `container_endpoint` when set, `host_endpoint` when `None`
- [x] 1.2 IMPL: Rename `endpoint: str` → `host_endpoint: str`, add `container_endpoint: str | None = None`, add `resolved_endpoint` property: `container_endpoint if container_endpoint is not None else host_endpoint`

## 2. check() Uses resolved_endpoint
- [x] 2.1 TEST: Update `test_check_returns_false_when_connection_row_is_absent` and related tests — construct cap with renamed fields; add test proving check probes `container_endpoint` when set (not `host_endpoint`)
- [x] 2.2 IMPL: Update `check()` to parse `self.resolved_endpoint` for the reachability probe; update `endpoint` → `host_endpoint` in `rsplit` call
## 3. provide() Writes Distinct Endpoints to Plug vs Slot

- [x] 3.1 TEST: Add test in functional caps test proving `add_tunnel_plug` receives `container_endpoint` (or `host_endpoint` as default) and `add_tunnel_slot` receives `host_endpoint`
- [x] 3.2 IMPL: Update `provide()` to pass `self.resolved_endpoint` to `add_tunnel_plug` and `self.host_endpoint` to `add_tunnel_slot`

- [x] 4.1 TEST: Update config round-trip test — YAML fixture with `host_endpoint` and optional `container_endpoint`; assert both fields deserialize correctly
- [x] 4.2 IMPL: Update `dec_hook` in `microjail.py` if needed; verify `msgspec.convert` handles new fields (likely no code change required)

- [x] 5.1 Update `tests/unit/test_endpoint_capability.py` — rename `endpoint=` → `host_endpoint=` in all remaining constructor calls and YAML fixtures
- [x] 5.2 Update `tests/unit/test_cap_contract.py` — rename `endpoint=` → `host_endpoint=` in constructor call
- [x] 5.3 Update `tests/functional/caps/test_endpoint_capability.py` — rename `endpoint=` → `host_endpoint=` in `cap()` helper and all call sites
- [x] 5.4 Update `tests/functional/commands/test_config_schema.py` — rename YAML fixture field and assertion
- [x] 5.5 Update `tests/e2e/test_endpoint_capability.py` — rename `endpoint=` → `host_endpoint=` in constructor calls
- [x] 5.6 Update `CONTEXT.md` Endpoint capability definition to reflect split fields
- [x] 5.7 Verify `revoke()` needs no field changes (only uses `self.name`, not endpoint)
- [x] 6.1 Run `uv run pytest` and fix any remaining failures
- [x] 6.2 Run `uv run pytest --slow` to confirm E2E tests pass
