"""Unit tests for opencode.jsonc generator."""

import json

from microjail.config.opencode import (
    DISABLED_PROVIDERS,
    generate_opencode_config,
)


def _parse(json_str: str) -> dict:  # type: ignore[type-arg]
    return json.loads(json_str)


def test_schema_present() -> None:
    """$schema key is present."""
    doc = _parse(generate_opencode_config("http://127.0.0.1:8080/v1"))
    assert "$schema" in doc


def test_llama_cpp_provider_present() -> None:
    """llama.cpp provider entry is present."""
    doc = _parse(generate_opencode_config("http://127.0.0.1:8080/v1"))
    assert "llama.cpp" in doc["provider"]


def test_llama_cpp_no_npm_field() -> None:
    """llama.cpp provider has no 'npm' field (no ai-sdk install required)."""
    doc = _parse(generate_opencode_config("http://127.0.0.1:8080/v1"))
    assert "npm" not in doc["provider"]["llama.cpp"]


def test_base_url_set() -> None:
    """BaseURL is set to the provided socket_url."""
    url = "http://127.0.0.1:8080/v1"
    doc = _parse(generate_opencode_config(url))
    assert doc["provider"]["llama.cpp"]["options"]["baseURL"] == url


def test_all_remote_providers_disabled() -> None:
    """Every provider in DISABLED_PROVIDERS has enabled: false."""
    doc = _parse(generate_opencode_config("http://127.0.0.1:8080/v1"))
    for provider_id in DISABLED_PROVIDERS:
        assert provider_id in doc["provider"], (
            f"Missing disabled provider: {provider_id}"
        )
        assert doc["provider"][provider_id].get("enabled") is False, (
            f"Provider '{provider_id}' is not explicitly disabled"
        )


def test_no_remote_providers_enabled() -> None:
    """No provider other than llama.cpp has enabled != false."""
    doc = _parse(generate_opencode_config("http://127.0.0.1:8080/v1"))
    for pid, pconf in doc["provider"].items():
        if pid == "llama.cpp":
            continue
        assert pconf.get("enabled") is False, (
            f"Provider '{pid}' is not disabled: {pconf}"
        )


def test_context_mode_plugin_present() -> None:
    """context-mode plugin is in the plugin list."""
    doc = _parse(generate_opencode_config("http://127.0.0.1:8080/v1"))
    assert "context-mode" in doc["plugin"]


def test_cc_safety_net_plugin_present() -> None:
    """cc-safety-net plugin is in the plugin list."""
    doc = _parse(generate_opencode_config("http://127.0.0.1:8080/v1"))
    assert "cc-safety-net" in doc["plugin"]


def test_output_is_valid_json() -> None:
    """Output is parseable JSON."""
    json_str = generate_opencode_config("http://127.0.0.1:8080/v1")
    doc = _parse(json_str)
    assert isinstance(doc, dict)
