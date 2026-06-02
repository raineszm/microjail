"""Gate: verify that ``opencode.jsonc`` is not writable by the workload.

Applies only when the environment was initialised with ``--agent opencode``.
Checks host-side filesystem permissions on the config file so the workload
cannot alter its own jail configuration.
"""

from typing import TYPE_CHECKING

from microjail.gates import GateResult

if TYPE_CHECKING:
    from pathlib import Path

_CONFIG_FILE = "opencode.jsonc"


def check_config_readonly(workspace: Path) -> GateResult:
    """Return a :class:`~microjail.gates.GateResult` confirming opencode.jsonc is readonly.

    Checks the ``opencode.jsonc`` file in *workspace* is not world-writable
    (mode bit ``o+w``).  This is checked from the host side because the file
    lives in the bind-mounted workspace — host permissions govern what the
    container can do with it.
    """
    config_path = workspace / _CONFIG_FILE

    if not config_path.exists():
        return GateResult(
            name="config-readonly",
            passed=False,
            message=(
                f"'{_CONFIG_FILE}' not found in workspace '{workspace}'. "
                "Expected it to have been written by 'microjail init --agent opencode'."
            ),
        )

    # stat() the file and check the world-write bit (0o002).
    mode = config_path.stat().st_mode
    world_writable = bool(mode & 0o002)

    if world_writable:
        return GateResult(
            name="config-readonly",
            passed=False,
            message=(
                f"'{_CONFIG_FILE}' is world-writable (mode {oct(mode)}). "
                "The agent could modify its own jail configuration. "
                f"Fix with: chmod o-w {config_path}"
            ),
        )

    return GateResult(
        name="config-readonly",
        passed=True,
        message=f"'{_CONFIG_FILE}' is not world-writable (mode {oct(mode)}).",
    )
