"""Accessibility handoff plugin.

Registers an A/B/C-only human handoff tool for gateway accessibility workflows.
The tool is intentionally decision-neutral: it asks the human operator to pick
one of up to three operator-authored actions and returns that selection. It does
not solve CAPTCHAs or infer challenge answers.
"""

from __future__ import annotations

from plugins.accessibility_handoff.tools import (
    ACCESSIBILITY_HANDOFF_SCHEMA,
    accessibility_handoff,
)


def register(ctx) -> None:
    ctx.register_tool(
        name="accessibility_handoff",
        toolset="accessibility",
        schema=ACCESSIBILITY_HANDOFF_SCHEMA,
        handler=accessibility_handoff,
        emoji="♿",
    )
