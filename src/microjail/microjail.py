"""The MicroJail configuration object and its on-disk persistence."""

from dataclasses import dataclass
from pathlib import Path

import msgspec

# Needed at runtime by msgspec for struct field resolution.
from microjail.gates.base import Gate
from microjail.gates.network_drop import NetworkDrop
from microjail.lockdown import Lockdown  # noqa: TC001

CONFIG_DIRNAME = ".microjail"
CONFIG_FILENAME = "config.yaml"


@dataclass(frozen=True)
class ConfigNotFoundError(Exception):
    """Raised when no microjail config exists for a project."""

    project_path: Path


def enc_hook(obj: object) -> object:
    """Serialize types msgspec does not handle natively."""
    if isinstance(obj, Path):
        return str(obj)
    raise NotImplementedError(f"cannot encode object of type {type(obj).__name__}")


def dec_hook(expected: type, obj: object) -> object:
    """Deserialize types msgspec does not handle natively."""
    if expected is Path:
        return Path(str(obj))
    if expected is Gate:
        return msgspec.convert(obj, type=NetworkDrop)
    raise NotImplementedError(f"cannot decode object of type {expected.__name__}")


class MicroJail(msgspec.Struct):
    """Configuration for a single microjail.

    Parameters
    ----------
    name:
        Name of the associated workshop.
    project_path:
        Path to the workshop project that this microjail governs.
    lockdown:
        The policy applied while workloads execute.
    """

    name: str
    project_path: Path
    lockdown: Lockdown

    @property
    def config_dir(self) -> Path:
        return self.project_path / CONFIG_DIRNAME

    @property
    def config_path(self) -> Path:
        return self.config_dir / CONFIG_FILENAME

    def save(self) -> None:
        """Persist this microjail to ``.microjail/config.yaml``."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path.write_bytes(msgspec.yaml.encode(self, enc_hook=enc_hook))

    @classmethod
    def load(cls, project_path: Path) -> MicroJail:
        """Load the microjail config stored under ``project_path``.

        Raises
        ------
        ConfigNotFoundError:
            If no ``.microjail/config.yaml`` exists for the project.
        """
        config_path = project_path / CONFIG_DIRNAME / CONFIG_FILENAME
        try:
            raw = config_path.read_bytes()
        except FileNotFoundError as exc:
            raise ConfigNotFoundError(project_path=project_path) from exc

        return msgspec.yaml.decode(raw, type=cls, dec_hook=dec_hook)
