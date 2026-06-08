"""Gate base class and registry."""

from microjail.gates.base import Gate
from microjail.gates.readonly_config import ReadonlyConfig

__all__ = ["Gate", "ReadonlyConfig"]
