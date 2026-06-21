"""Backward-compatible WhatsApp adapter import path.

The WhatsApp transport now lives in ``plugins.platforms.whatsapp.adapter`` so it
can be managed by the platform plugin system.  Sebastian's carried local session
patches and some older tests/importers still import ``gateway.platforms.whatsapp``;
keep that path as a thin re-export to avoid dropping the local behavior during
upgrades.
"""

from plugins.platforms.whatsapp.adapter import (  # noqa: F401
    WhatsAppAdapter,
    _WhatsAppSession,
    _WhatsAppSessionRoute,
    check_whatsapp_requirements,
)

__all__ = [
    "WhatsAppAdapter",
    "_WhatsAppSession",
    "_WhatsAppSessionRoute",
    "check_whatsapp_requirements",
]
