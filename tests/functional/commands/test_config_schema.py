"""Tests that documented YAML config shapes load into the expected runtime types."""

from pathlib import Path  # noqa: TC003

from microjail.caps.endpoint import WorkshopEndpointCapability
from microjail.gates.network_drop import NetworkDrop
from microjail.gates.readonly_config import ReadonlyConfig
from microjail.microjail import MicroJail


def write_config(project: Path) -> None:
    config = project / ".microjail" / "config.yaml"
    config.parent.mkdir()
    config.write_text(
        f"""workshop:
  name: mj-workshop
  project: {project}
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


def test_documented_endpoint_capability_config_shape_parses(tmp_path: Path) -> None:
    write_config(tmp_path)

    mj = MicroJail.load(tmp_path)
    cap_obj = mj.lockdown.caps[0]

    assert isinstance(cap_obj, WorkshopEndpointCapability)
    assert cap_obj.name == "inference"
    assert cap_obj.host_endpoint == "127.0.0.1:8080"


def test_documented_default_gate_config_shape_parses(tmp_path: Path) -> None:
    write_config(tmp_path)

    mj = MicroJail.load(tmp_path)

    assert [type(gate) for gate in mj.lockdown.gates] == [NetworkDrop, ReadonlyConfig]
