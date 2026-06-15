from typing import TYPE_CHECKING
from unittest.mock import Mock

from typer.testing import CliRunner

from microjail.caps.endpoint import WorkshopEndpointCapability
from microjail.cli import app
from microjail.gates.network_drop import NetworkDrop
from microjail.gates.readonly_config import ReadonlyConfig
from microjail.microjail import ApplicationStatus, MicroJail

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
    - type: endpoint-tunnel
      name: inference
      host_endpoint: 127.0.0.1:8080
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

    async def ensure_lockdown(microjail: MicroJail, _intent):
        seen["cap"] = microjail.lockdown.caps[0]
        return Mock(status=ApplicationStatus.SUCCESS, gates_enforced=2)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(MicroJail, "ensure", ensure_lockdown)

    result = CliRunner().invoke(app, ["lock"])

    assert result.exit_code == 0
    assert isinstance(seen["cap"], WorkshopEndpointCapability)
    assert seen["cap"].name == "inference"
    assert seen["cap"].host_endpoint == "127.0.0.1:8080"


def test_cli_loads_documented_default_gate_config_shape(
    tmp_path: Path, monkeypatch
) -> None:
    write_config(tmp_path)
    seen = {}

    async def ensure_lockdown(microjail: MicroJail, _intent):
        seen["gates"] = microjail.lockdown.gates
        return Mock(status=ApplicationStatus.SUCCESS, gates_enforced=2)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(MicroJail, "ensure", ensure_lockdown)

    result = CliRunner().invoke(app, ["lock"])

    assert result.exit_code == 0
    assert [type(gate) for gate in seen["gates"]] == [NetworkDrop, ReadonlyConfig]
