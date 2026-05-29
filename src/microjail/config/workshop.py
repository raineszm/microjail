"""Generate workshop.yaml for a microjail environment."""

import io
from typing import TYPE_CHECKING

from ruamel.yaml import YAML

if TYPE_CHECKING:
    from microjail.config.models import EnvironmentConfig


def generate_workshop_yaml(config: EnvironmentConfig) -> str:
    """Return a workshop.yaml string for the given *config*.

    Rules (from data-model.md):
    - ``name`` and ``base`` are always set.
    - ``sdks`` includes ``opencode`` (latest/stable) and ``skills`` (latest/edge)
      only when ``config.agent == "opencode"``.
    - No ``system`` SDK, no tunnel/plugs/slots entries.
    """
    sdks: list[dict[str, str]] = []
    if config.agent == "opencode":
        sdks = [
            {"name": "opencode", "channel": "latest/stable"},
            {"name": "skills", "channel": "latest/edge"},
        ]

    doc: dict[str, object] = {
        "name": config.name,
        "base": config.base_image,
        "sdks": sdks,
    }

    yaml = YAML()
    yaml.default_flow_style = False
    buf = io.StringIO()
    yaml.dump(doc, buf)
    return buf.getvalue()
