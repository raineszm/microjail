from typing import TYPE_CHECKING

import pytest

from microjail.adapters.workshop import Workshop
from microjail.gates.network_drop import NetworkDrop
from microjail.gates.readonly_config import ReadonlyConfig
from microjail.lockdown import Lockdown
from microjail.microjail import ConfigNotFoundError, MicroJail

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def tmp_microjail(tmp_path: Path, project_name: str) -> MicroJail:
    return MicroJail(
        workshop=Workshop(name=project_name, project=tmp_path),
        lockdown=Lockdown(caps=[], gates=[]),
    )


def test_save_writes_config_under_microjail_dir(tmp_microjail: MicroJail) -> None:
    tmp_microjail.save()
    assert tmp_microjail.config_path.exists()


def test_save_creates_missing_microjail_dir(tmp_microjail: MicroJail) -> None:
    tmp_microjail.save()

    assert tmp_microjail.config_dir.is_dir()


def test_load_round_trips_saved_config(tmp_microjail: MicroJail) -> None:
    tmp_microjail.save()

    loaded = MicroJail.load(tmp_microjail.project_path)
    assert loaded == tmp_microjail


def test_load_round_trips_default_gates(tmp_path: Path, project_name: str) -> None:
    microjail = MicroJail(
        workshop=Workshop(name=project_name, project=tmp_path),
        lockdown=Lockdown.default(),
    )
    microjail.save()

    loaded = MicroJail.load(tmp_path)
    assert loaded.name == microjail.name
    assert loaded.project_path == microjail.project_path
    assert isinstance(loaded.lockdown.gates[0], NetworkDrop)
    assert isinstance(loaded.lockdown.gates[1], ReadonlyConfig)


def test_load_raises_when_config_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigNotFoundError) as exc_info:
        MicroJail.load(tmp_path)

    assert exc_info.value.project_path == tmp_path
