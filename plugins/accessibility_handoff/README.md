# Accessibility Handoff Plugin

The `accessibility_handoff` plugin adds a gateway-safe human handoff tool for visual gates where the operator can only respond from chat.

## Contract

- The tool accepts one to three concrete actions.
- The prompt labels them `A`, `B`, and `C`.
- The prompt instructs the human to reply with exactly one letter.
- The tool deliberately calls the clarify callback without a structured choices menu so gateway fallbacks do not add numbers or `Other` free text.
- Replies are accepted only when they normalize to `A`, `B`, or `C`; numbers and free text are rejected and reprompted.
- Optional screenshots can be attached by passing `screenshot_path`; the prompt emits `MEDIA:/absolute/path` so messaging adapters deliver a native attachment.

## Browser expectation

This workflow is for accessibility / remote operation, not autonomous CAPTCHA solving. The human remains the decision-maker and Hermes performs only the selected action.

For visual human-verification gates, use a persistent headed Chrome/Chromium CDP session. The guard rejects obvious unsuitable modes:

- `browser.engine: lightpanda`
- `browser.headless: true`
- configured CDP endpoints whose `/json/version` user agent contains `HeadlessChrome`

If the guard blocks a call, start or connect a headed browser first, for example via Hermes `/browser connect` or by configuring `browser.cdp_url` to a reachable headed Chrome/Chromium debug endpoint.

## Example tool call shape

```json
{
  "question": "Human verification needed.",
  "choices": ["click the checkbox", "reload the challenge", "switch to audio challenge"],
  "screenshot_path": "/tmp/handoff.png"
}
```

The user-facing message is shaped like:

```text
MEDIA:/tmp/handoff.png

Human verification needed.

A — click the checkbox
B — reload the challenge
C — switch to audio challenge

Reply with exactly one letter: A, B, or C.
```
