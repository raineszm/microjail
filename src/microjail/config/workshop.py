"""Generate workshop.yaml and sdk.yaml for a microjail environment."""

import io
from typing import TYPE_CHECKING

from ruamel.yaml import YAML

if TYPE_CHECKING:
    from microjail.config.models import EnvironmentConfig

# Plug/slot reference strings for the inference tunnel.
# Used by ``microjail init`` (post-launch connect) and ``ctf/main.py``
# (connect call) so the naming is defined in one place.
INFERENCE_PLUG_REF: str = "local-inference:llama"
INFERENCE_SLOT_REF: str = "system:llama"


def generate_workshop_yaml(config: EnvironmentConfig) -> str:
    """Return a workshop.yaml string for the given *config*.

    Rules:
    - ``name`` and ``base`` are always set.
    - When ``config.agent == "opencode"``, ``sdks`` includes ``opencode``
      (latest/stable) and ``skills`` (latest/edge).
    - When ``config.agent == "omp"``, ``sdks`` includes ``omp`` (14/edge);
      no ``skills`` entry is emitted.
    - When ``config.inference`` is set, a ``project-local-inference`` SDK
      reference and a ``system`` SDK with a tunnel slot are appended.
      The slot endpoint is ``config.inference_endpoint`` or ``localhost:8080``.
    """
    sdks: list[dict[str, object]] = []
    if config.agent == "opencode":
        sdks = [
            {"name": "opencode", "channel": "latest/stable"},
            {"name": "skills", "channel": "latest/edge"},
        ]
    elif config.agent == "omp":
        sdks = [{"name": "omp", "channel": "14/edge"}]

    if config.inference is not None:
        endpoint = config.inference_endpoint or "localhost:8080"
        sdks.append({"name": "project-local-inference"})
        sdks.append(
            {
                "name": "system",
                "slots": {
                    "llama": {
                        "interface": "tunnel",
                        "endpoint": endpoint,
                    },
                },
            }
        )

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


def generate_sdk_yaml(config: EnvironmentConfig) -> str:
    """Return the `.workshop/local-inference/sdk.yaml` content for *config*.

    Returns an empty string when ``config.inference`` is ``None`` — the
    caller is responsible for gating the write on ``inference is not None``.

    Raises :exc:`ValueError` when ``config.inference_endpoint`` is set but
    contains no ``:`` separator (malformed ``host:port`` value).
    """
    if config.inference is None:
        return ""

    endpoint = config.inference_endpoint or "localhost:8080"
    _, sep, port_str = endpoint.rpartition(":")
    if not sep:
        raise ValueError(
            f"inference_endpoint {endpoint!r} contains no port separator ':'"
        )

    doc: dict[str, object] = {
        "name": "local-inference",
        "plugs": {
            "llama": {
                "interface": "tunnel",
                "endpoint": f"localhost:{port_str}",
            },
        },
    }

    yaml = YAML()
    yaml.default_flow_style = False
    buf = io.StringIO()
    yaml.dump(doc, buf)
    return buf.getvalue()
