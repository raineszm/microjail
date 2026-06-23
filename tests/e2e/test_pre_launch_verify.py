from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

    from microjail.adapters.workshop import Workshop

from typer.testing import CliRunner

from microjail import policy
from microjail.caps.endpoint import WorkshopEndpointCapability
from microjail.cli import app
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail
from tests.marks import requires_lxd, requires_workshop

pytestmark = [
    requires_lxd(),
    requires_workshop(),
]


def test_exec_fails_pre_launch_verify_fatal_capability(
    e2e_workshop: Workshop,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GIVEN a fatal capability that points to a non-existent port (will fail reachability check)
    mj = MicroJail(
        workshop=e2e_workshop,
        lockdown=Lockdown(
            caps=[
                WorkshopEndpointCapability(
                    name="bad-endpoint",
                    host_endpoint="127.0.0.1:9999",
                    fatal=True,
                )
            ],
            gates=Lockdown.default().gates,
        ),
    )
    mj.save()

    from microjail.gates.base import VerificationResult

    monkeypatch.setattr(
        WorkshopEndpointCapability,
        "verify",
        lambda _self, _mj: VerificationResult.FAILED,
    )

    # WHEN we try to run a command
    result = CliRunner().invoke(
        app,
        ["exec", "--", "sh", "-c", "touch /project/started"],
    )

    # THEN it fails pre-launch verification
    assert result.exit_code == policy.CAPABILITY_APPLICATION_FAILURE
    assert "exec failed: capability" in result.stderr
    assert "bad-endpoint" in result.stderr
    assert not (e2e_workshop.project / "started").exists()


def test_exec_warns_pre_launch_verify_non_fatal_capability(
    e2e_workshop: Workshop,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GIVEN a non-fatal capability that points to a non-existent port (will fail reachability check)
    mj = MicroJail(
        workshop=e2e_workshop,
        lockdown=Lockdown(
            caps=[
                WorkshopEndpointCapability(
                    name="bad-endpoint",
                    host_endpoint="127.0.0.1:9999",
                    fatal=False,
                )
            ],
            gates=Lockdown.default().gates,
        ),
    )
    mj.save()

    from microjail.gates.base import VerificationResult

    monkeypatch.setattr(
        WorkshopEndpointCapability,
        "verify",
        lambda _self, _mj: VerificationResult.FAILED,
    )

    # WHEN we run a command
    result = CliRunner().invoke(
        app,
        ["exec", "--", "sh", "-c", "touch /project/started"],
    )

    # THEN it succeeds but warns about the failing capability
    assert result.exit_code == 0
    assert "warning: bad-endpoint" in result.stderr
    assert (e2e_workshop.project / "started").exists()
