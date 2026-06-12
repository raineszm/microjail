## Slice 1: Basic popen functionality and background execution

- [x] 1.1 RED: `test_popen_executes_command_in_background`, `test_microjail_popen_executes_command_in_background`, and `test_popen_interactive_direct_inheritance`
- [x] 1.2 GREEN: implement `workshop.popen` (supporting `interactive` parameter) and `MicroJail.popen` to run commands non-blockingly
- [x] 1.3 REFACTOR: none

## Slice 2: Standard streams interaction

- [x] 2.1 RED: `test_popen_interacts_with_standard_streams`
- [x] 2.2 GREEN: ensure `**kwargs` is passed to `subprocess.Popen` in `workshop.popen`
- [x] 2.3 REFACTOR: none

## Slice 3: Exception and error cases

- [x] 3.1 RED: `test_popen_fails_if_workshop_does_not_exist` and `test_popen_fails_if_workshop_is_not_launched`
- [x] 3.2 GREEN: add exists and launch status checks in `workshop.popen`
- [x] 3.3 REFACTOR: extract common workshop state validation function in `workshop.py` shared by `exec_` and `popen`
