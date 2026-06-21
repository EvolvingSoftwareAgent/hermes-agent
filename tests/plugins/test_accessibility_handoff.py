import json

import pytest


class _Callback:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, question, choices):
        self.calls.append((question, choices))
        return self.responses.pop(0)


def test_build_prompt_limits_user_reply_to_abc_only():
    from plugins.accessibility_handoff.tools import build_abc_prompt

    prompt = build_abc_prompt(
        "Human verification needed.",
        ["click the checkbox", "reload challenge", "switch to audio"],
        screenshot_path="/tmp/gate.png",
    )

    assert "MEDIA:/tmp/gate.png" in prompt
    assert "A — click the checkbox" in prompt
    assert "B — reload challenge" in prompt
    assert "C — switch to audio" in prompt
    assert "Reply with exactly one letter: A, B, or C." in prompt
    assert "Other" not in prompt
    assert "free" not in prompt.lower()
    assert "1." not in prompt


def test_normalize_response_accepts_only_letters_not_numbers_or_free_text():
    from plugins.accessibility_handoff.tools import normalize_abc_response

    assert normalize_abc_response("a", 3) == "A"
    assert normalize_abc_response(" B ", 3) == "B"
    assert normalize_abc_response("C.", 3) == "C"

    with pytest.raises(ValueError, match="Reply with exactly A, B, or C"):
        normalize_abc_response("1", 3)
    with pytest.raises(ValueError, match="Reply with exactly A or B"):
        normalize_abc_response("C", 2)
    with pytest.raises(ValueError, match="Reply with exactly A, B, or C"):
        normalize_abc_response("click checkbox", 3)


def test_accessibility_handoff_reprompts_until_valid_abc_without_choices_menu():
    from plugins.accessibility_handoff.tools import accessibility_handoff

    callback = _Callback(["click checkbox", "B"])

    result = json.loads(accessibility_handoff(
        {
            "question": "Human verification needed.",
            "choices": ["click checkbox", "reload challenge", "switch to audio"],
            "max_attempts": 2,
            "require_headed_browser": False,
        },
        clarify_callback=callback,
    ))

    assert result == {"selected": "B", "choice": "reload challenge"}
    assert len(callback.calls) == 2
    for question, choices in callback.calls:
        assert choices is None
        assert "Reply with exactly one letter: A, B, or C." in question


def test_accessibility_handoff_rejects_more_than_three_choices():
    from plugins.accessibility_handoff.tools import accessibility_handoff

    result = json.loads(accessibility_handoff(
        {
            "question": "Pick one.",
            "choices": ["one", "two", "three", "four"],
        },
        clarify_callback=_Callback(["A"]),
    ))

    assert result["error"] == "accessibility_handoff supports 1 to 3 choices only"


def test_browser_mode_guard_rejects_headless_and_lightpanda():
    from plugins.accessibility_handoff.tools import validate_headed_browser_config

    assert validate_headed_browser_config({"browser": {"engine": "chrome", "headless": False}})["ok"] is True

    headless = validate_headed_browser_config({"browser": {"engine": "chrome", "headless": True}})
    assert headless["ok"] is False
    assert "headed" in headless["error"]

    lightpanda = validate_headed_browser_config({"browser": {"engine": "lightpanda"}})
    assert lightpanda["ok"] is False
    assert "Lightpanda" in lightpanda["error"]


def test_cdp_version_guard_rejects_headlesschrome_user_agent(monkeypatch):
    from plugins.accessibility_handoff import tools

    def fake_fetch(url):
        assert url == "http://127.0.0.1:9222"
        return {"User-Agent": "Mozilla/5.0 HeadlessChrome/148.0.0.0"}

    monkeypatch.setattr(tools, "_fetch_cdp_version", fake_fetch)

    result = tools.validate_headed_browser_config({"browser": {"cdp_url": "http://127.0.0.1:9222"}})

    assert result["ok"] is False
    assert "HeadlessChrome" in result["error"]


def test_cdp_version_guard_accepts_normal_chrome_user_agent(monkeypatch):
    from plugins.accessibility_handoff import tools

    monkeypatch.setattr(
        tools,
        "_fetch_cdp_version",
        lambda url: {"User-Agent": "Mozilla/5.0 Chrome/148.0.0.0 Safari/537.36"},
    )

    result = tools.validate_headed_browser_config({"browser": {"cdp_url": "http://127.0.0.1:9223"}})

    assert result["ok"] is True
    assert result["cdp_url"] == "http://127.0.0.1:9223"
