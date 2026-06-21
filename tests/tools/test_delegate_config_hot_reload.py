from __future__ import annotations

import sys
import types


def test_delegation_file_config_overrides_stale_cli_config(monkeypatch):
    from tools import delegate_tool

    fake_cli = types.SimpleNamespace(
        CLI_CONFIG={
            "delegation": {
                "model": "stale-model",
                "child_timeout_seconds": 600,
                "max_concurrent_children": 3,
            }
        }
    )
    fake_config = types.SimpleNamespace(
        load_config=lambda: {
            "delegation": {
                "model": "fresh-model",
                "child_timeout_seconds": 1800,
                "max_concurrent_children": 2,
            }
        }
    )
    monkeypatch.setitem(sys.modules, "cli", fake_cli)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", fake_config)

    cfg = delegate_tool._load_config()

    assert cfg["model"] == "fresh-model"
    assert cfg["child_timeout_seconds"] == 1800
    assert cfg["max_concurrent_children"] == 2


def test_delegation_file_config_keeps_runtime_defaults_when_missing(monkeypatch):
    from tools import delegate_tool

    fake_cli = types.SimpleNamespace(
        CLI_CONFIG={
            "delegation": {
                "provider": "nvidia",
                "reasoning_effort": "none",
            }
        }
    )
    fake_config = types.SimpleNamespace(load_config=lambda: {"delegation": {"model": "fresh-model"}})
    monkeypatch.setitem(sys.modules, "cli", fake_cli)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", fake_config)

    cfg = delegate_tool._load_config()

    assert cfg["model"] == "fresh-model"
    assert cfg["provider"] == "nvidia"
    assert cfg["reasoning_effort"] == "none"
