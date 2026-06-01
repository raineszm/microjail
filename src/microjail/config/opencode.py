"""Generate opencode.jsonc for a microjail environment."""

import json

# All known remote providers that must be explicitly disabled.
DISABLED_PROVIDERS: tuple[str, ...] = (
    "anthropic",
    "openai",
    "google",
    "amazon-bedrock",
    "azure",
    "groq",
    "mistral",
    "xai",
    "deepseek",
    "cerebras",
)


def generate_opencode_config(socket_url: str | None = None) -> str:
    """Return an opencode.jsonc string configured for local inference.

    Parameters
    ----------
    socket_url:
        The inference endpoint URL (e.g. ``http://127.0.0.1:8080/v1``).
        When provided, a ``llama.cpp`` provider entry is added with
        ``options["baseURL"]`` set to this value.
        When ``None`` (no ``--inference llama-cpp``), the ``llama.cpp``
        provider is omitted entirely.

    Rules (from data-model.md):
    - All providers in :data:`DISABLED_PROVIDERS` set ``enabled: false``.
    - ``llama.cpp`` provider has no ``npm`` field; uses built-in provider mechanism.
    - ``plugin`` list always contains ``context-mode`` and ``cc-safety-net``.

    """
    provider: dict[str, object] = {
        pid: {"enabled": False} for pid in DISABLED_PROVIDERS
    }
    if socket_url is not None:
        provider["llama.cpp"] = {
            "name": "llama-server (local)",
            "options": {"baseURL": socket_url},
            "models": {},
        }

    doc: dict[str, object] = {
        "$schema": "https://opencode.ai/config.json",
        "provider": provider,
        "plugin": ["context-mode", "cc-safety-net"],
    }

    return json.dumps(doc, indent=4)
