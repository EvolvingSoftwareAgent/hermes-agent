"""A/B/C-only accessibility handoff helpers and tool handler."""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Any, Callable, Iterable, Mapping

ABC_LABELS = ("A", "B", "C")

ACCESSIBILITY_HANDOFF_SCHEMA = {
    "name": "accessibility_handoff",
    "description": (
        "Accessibility handoff for human-verification or other visual gates. "
        "Use when the user can only operate through chat: provide 1-3 concrete "
        "actions labelled by the tool as A/B/C, optionally include a browser "
        "screenshot path, and wait for the human to reply with exactly A, B, or C. "
        "Do not use this to autonomously solve CAPTCHA puzzles; the human chooses."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Short context for the human, e.g. 'Human verification needed.'",
            },
            "choices": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 3,
                "description": "One to three concrete actions. The tool labels them A/B/C.",
            },
            "screenshot_path": {
                "type": "string",
                "description": "Optional local screenshot path to deliver as MEDIA:<path> in the prompt.",
            },
            "max_attempts": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "default": 3,
                "description": "How many invalid replies to reprompt before returning an error.",
            },
            "require_headed_browser": {
                "type": "boolean",
                "default": True,
                "description": "If true, include headed-browser guidance in errors when config is not suitable.",
            },
        },
        "required": ["question", "choices"],
    },
}


def _clean_choices(raw_choices: Iterable[Any]) -> list[str]:
    choices = [str(choice).strip() for choice in (raw_choices or [])]
    return [choice for choice in choices if choice]


def _expected_letters(count: int) -> str:
    letters = list(ABC_LABELS[:count])
    if count == 1:
        return letters[0]
    if count == 2:
        return f"{letters[0]} or {letters[1]}"
    return f"{letters[0]}, {letters[1]}, or {letters[2]}"


def build_abc_prompt(question: str, choices: Iterable[Any], screenshot_path: str = "") -> str:
    """Return a WhatsApp-friendly prompt whose only valid replies are A/B/C."""
    clean = _clean_choices(choices)
    if not 1 <= len(clean) <= 3:
        raise ValueError("accessibility_handoff supports 1 to 3 choices only")

    lines: list[str] = []
    if screenshot_path:
        lines.append(f"MEDIA:{screenshot_path}")
        lines.append("")
    lines.append(str(question or "Accessibility handoff needed.").strip())
    lines.append("")
    for label, choice in zip(ABC_LABELS, clean):
        lines.append(f"{label} — {choice}")
    lines.append("")
    lines.append(f"Reply with exactly one letter: {_expected_letters(len(clean))}.")
    return "\n".join(lines)


def normalize_abc_response(response: Any, choice_count: int) -> str:
    """Normalize a reply to A/B/C and reject numbers/free text."""
    if not 1 <= int(choice_count) <= 3:
        raise ValueError("accessibility_handoff supports 1 to 3 choices only")
    text = str(response or "").strip().upper()
    # Allow light punctuation from mobile keyboards, but not words/numbers.
    text = re.sub(r"[\s\.!?]+$", "", text)
    valid = set(ABC_LABELS[: int(choice_count)])
    if text in valid:
        return text
    raise ValueError(f"Reply with exactly {_expected_letters(int(choice_count))}")


def _fetch_cdp_version(cdp_url: str) -> dict[str, Any]:
    """Fetch /json/version from a CDP HTTP endpoint."""
    url = str(cdp_url or "").strip().rstrip("/")
    if not url:
        return {}
    if url.startswith("ws://") or url.startswith("wss://"):
        # Convert browser WebSocket URL to the adjacent HTTP origin when possible.
        scheme = "https" if url.startswith("wss://") else "http"
        rest = url.split("://", 1)[1].split("/devtools/", 1)[0]
        url = f"{scheme}://{rest}"
    if "://" not in url:
        url = f"http://{url}"
    with urllib.request.urlopen(f"{url}/json/version", timeout=2) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def validate_headed_browser_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Check whether config appears suitable for visual accessibility handoff."""
    cfg = dict(config or {})
    browser = cfg.get("browser") if isinstance(cfg.get("browser"), Mapping) else {}
    browser = dict(browser or {})
    engine = str(browser.get("engine", "auto") or "auto").lower()
    if engine == "lightpanda":
        return {
            "ok": False,
            "error": "Lightpanda is not suitable for accessibility handoff; use a persistent headed Chrome/Chromium CDP session.",
        }
    if bool(browser.get("headless", False)):
        return {
            "ok": False,
            "error": "Accessibility handoff requires a headed browser session, not headless mode.",
        }
    cdp_url = str(browser.get("cdp_url") or "").strip()
    if cdp_url:
        try:
            version = _fetch_cdp_version(cdp_url)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"Configured CDP browser is not reachable for accessibility handoff: {type(exc).__name__}: {exc}",
            }
        user_agent = str(version.get("User-Agent") or "")
        if "HeadlessChrome" in user_agent:
            return {
                "ok": False,
                "error": "Configured CDP browser reports HeadlessChrome; accessibility handoff requires a proper headed Chrome/Chromium session.",
            }
        return {"ok": True, "engine": engine, "cdp_url": cdp_url}
    return {"ok": True, "engine": engine}


def _load_runtime_config() -> dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def accessibility_handoff(
    args: Mapping[str, Any],
    *,
    clarify_callback: Callable[[str, Any], str] | None = None,
    **_kwargs: Any,
) -> str:
    """Tool handler: prompt the user until they answer A/B/C, then return selection."""
    choices = _clean_choices(args.get("choices", []))
    if not 1 <= len(choices) <= 3:
        return json.dumps({"error": "accessibility_handoff supports 1 to 3 choices only"}, ensure_ascii=False)

    if args.get("require_headed_browser", True):
        browser_check = validate_headed_browser_config(_load_runtime_config())
        if not browser_check.get("ok"):
            return json.dumps(browser_check, ensure_ascii=False)

    question = str(args.get("question") or "Accessibility handoff needed.").strip()
    screenshot_path = str(args.get("screenshot_path") or "").strip()
    max_attempts = int(args.get("max_attempts") or 3)
    max_attempts = max(1, min(max_attempts, 5))

    prompt = build_abc_prompt(question, choices, screenshot_path=screenshot_path)
    if clarify_callback is None:
        return json.dumps({
            "error": "accessibility_handoff requires an interactive clarify callback",
            "prompt": prompt,
        }, ensure_ascii=False)

    last_error = ""
    for attempt in range(max_attempts):
        attempt_prompt = prompt
        if last_error:
            attempt_prompt = f"{last_error}\n\n{prompt}"
        # choices=None is deliberate: platform fallback must not add numbers or Other/free-text.
        response = clarify_callback(attempt_prompt, None)
        try:
            selected = normalize_abc_response(response, len(choices))
        except ValueError as exc:
            last_error = str(exc)
            continue
        idx = ABC_LABELS.index(selected)
        return json.dumps({"selected": selected, "choice": choices[idx]}, ensure_ascii=False)

    return json.dumps({"error": last_error or f"Reply with exactly {_expected_letters(len(choices))}"}, ensure_ascii=False)
