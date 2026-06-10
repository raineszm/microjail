from typing import TYPE_CHECKING
from unittest.mock import Mock

from typer.testing import CliRunner

from microjail.caps.endpoint import WorkshopEndpointCapability
from microjail.cli import app
from microjail.gates.network_drop import NetworkDrop
from microjail.gates.readonly_config import ReadonlyConfig
from microjail.microjail import MicroJail

if TYPE_CHECKING:
    from pathlib import Path


def write_config(project: Path) -> None:
    config = project / ".microjail" / "config.yaml"
    config.parent.mkdir()
    config.write_text(
        f"""name: mj-workshop
project_path: {project}
lockdown:
  caps:
    - type: endpoint-proxy
      name: inference
      endpoint: 127.0.0.1:8080
  gates:
    - name: network-egress
    - name: readonly-config
""",
        encoding="utf-8",
    )


def test_cli_loads_documented_endpoint_capability_config_shape(
    tmp_path: Path, monkeypatch
) -> None:
    write_config(tmp_path)
    seen = {}

    def ensure_for_lock(self: MicroJail):
        seen["cap"] = self.lockdown.caps[0]
        return Mock(capability_failures=[], gates_enforced=2, gate_failure=None)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(MicroJail, "ensure_for_lock", ensure_for_lock)

    result = CliRunner().invoke(app, ["lock"])

    assert result.exit_code == 0
    assert isinstance(seen["cap"], WorkshopEndpointCapability)
    assert seen["cap"].name == "inference"
    assert seen["cap"].endpoint == "127.0.0.1:8080"


def test_cli_loads_documented_default_gate_config_shape(
    tmp_path: Path, monkeypatch
) -> None:
    write_config(tmp_path)
    seen = {}

    def ensure_for_lock(self: MicroJail):
        seen["gates"] = self.lockdown.gates
        return Mock(capability_failures=[], gates_enforced=2, gate_failure=None)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(MicroJail, "ensure_for_lock", ensure_for_lock)

    result = CliRunner().invoke(app, ["lock"])

    assert result.exit_code == 0
    assert [type(gate) for gate in seen["gates"]] == [NetworkDrop, ReadonlyConfig]
