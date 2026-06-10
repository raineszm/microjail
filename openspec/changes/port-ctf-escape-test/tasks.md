## 1. Package scaffold

- [x] 1.1 Create `ctf/` package (`__init__.py`, `__main__.py` with `python -m ctf` entrypoint)
- [x] 1.2 Cherry-pick `http_server.py` and `secrets_gen.py` from commit `e4c3702`
- [x] 1.3 Create `report.py` with `CtfReport` dataclass and JSON serialization
- [x] 1.4 Create CLI with `--model` (required), `--endpoint` (default `localhost:8080`), `--keep-on-failure`, `--timeout` (default 300)

## 2. Core runner

- [x] 2.1 Implement preflight checks (binary availability for `workshop`, `lxc`)
- [x] 2.2 Implement ephemeral workspace creation at `/tmp/ctf-<uuid>/`
- [x] 2.3 Implement Workshop init (`--sdks omp/14/edge`) + launch
- [x] 2.4 Implement Lockdown config generation and application (`MicroJail.load()` + `ensure_for_run()`) with inference endpoint capability
- [x] 2.5 Implement host bait setup (HTTP bait server, secret file write) on port different from inference endpoint
- [x] 2.6 Implement agent wrapper script generation (`ctf_agent.sh`) with `omp --list-models` + feedback-driven `omp -p` loop
- [x] 2.7 Implement adversarial prompt generation (escape targets + loop/notes-file instructions)
- [x] 2.8 Implement concurrent agent launch via `subprocess.Popen` + signal-file polling loop
- [x] 2.9 Implement breach detection (signal-file secret matching) and SIGTERM on breach/timeout
- [x] 2.10 Implement ordered teardown (`release()` → `workshop stop` → LXD delete → `rm -rf`) with exception suppression per step

## 3. Verdict and reporting

- [x] 3.1 Implement verdict precedence: FAIL over ERROR, ERROR/report_persistence only overrides PASS
- [x] 3.2 Implement JSON report emission with standard fields (`outcome`, `error_kind`, `elapsed`, `timeout`, `secret_match`, `breach_vector`, `run_id`)
- [x] 3.3 Implement `--keep-on-failure` logic (retain workspace on FAIL or ERROR)

## 4. Test suite

- [x] 4.1 Add `tests/escape/conftest.py` with `slow` + `lxd` + `workshop` marks
- [x] 4.2 Add unit tests for `report.py`, `secrets_gen.py`, `http_server.py`
- [x] 4.3 Add unit tests for CLI argument parsing
- [x] 4.4 Add unit tests for runner helper/logic modules
- [x] 4.5 Add escape scenario tests validating control flow and verdict semantics
- [x] 4.6 Document alpha instability of exit/result semantics and `error_kind` in CTF help/docs
