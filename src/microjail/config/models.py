"""Shared in-memory configuration types for microjail commands."""

from dataclasses import dataclass
from typing import Literal

InferenceBackend = Literal["llama-cpp"]
AgentHarness = Literal["opencode", "omp"]

SUPPORTED_INFERENCE: tuple[str, ...] = ("llama-cpp",)
SUPPORTED_AGENTS: tuple[str, ...] = ("opencode", "omp")


@dataclass(frozen=True)
class EnvironmentConfig:
    """Immutable representation of user intent captured from CLI arguments.

    Passed to all file generators and the workshop client. Never persisted
    directly; :class:`~microjail.state.EnvironmentState` is the persisted form.
    """

    name: str
    """Workshop environment name. Must match ``^[a-zA-Z][a-zA-Z0-9-]*$``, max 63 chars."""

    base_image: str
    """LXD base image string, e.g. ``ubuntu@26.04``. Fixed for P1."""

    inference: InferenceBackend | None
    """Inference backend, or ``None`` if not requested."""

    agent: AgentHarness | None
    """Agent harness, or ``None`` if not requested."""

    inference_endpoint: str | None = None
    """Host-side inference endpoint as ``host:port`` (no scheme, no path).

    ``None`` means default to ``localhost:8080`` in generated YAML.
    Populated from ``--inference-url`` by stripping scheme and path:
    ``http://192.168.1.5:9000/v1`` → ``"192.168.1.5:9000"``.
    Used by :func:`generate_workshop_yaml` (system slot endpoint) and
    :func:`generate_sdk_yaml` (plug endpoint port extraction).
    Never persisted; :attr:`EnvironmentState.socket_url` is derived from this.
    """
