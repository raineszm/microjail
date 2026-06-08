from microjail.gates.network_drop import NetworkDrop
from microjail.gates.readonly_config import ReadonlyConfig
from microjail.lockdown import Lockdown


def test_default_lockdown_drops_network() -> None:
    lockdown = Lockdown.default()

    assert lockdown.caps == []
    assert len(lockdown.gates) == 2
    assert isinstance(lockdown.gates[0], NetworkDrop)
    assert isinstance(lockdown.gates[1], ReadonlyConfig)
