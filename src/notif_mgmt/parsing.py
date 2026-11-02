"""Deterministic parsing of notification evidence into interaction candidates.

A parser only extracts what the notification actually states: platform, signal
kind, an actor candidate, and (when present) an exact identity value such as an
email address or @handle. A display name alone is NEVER an identity.
"""
import re

from pydantic import BaseModel

from .classify import _SOCIAL_HINTS, classify
from .models import InboundEvent

PARSER_NAME = "notification-rules"
PARSER_VERSION = "1"

_ACTOR_PATTERNS = [
    re.compile(r"^(.+?) sent you a (?:direct )?message", re.IGNORECASE),
    re.compile(r"^(.+?) messaged you", re.IGNORECASE),
    re.compile(r"^(.+?) has sent you a message", re.IGNORECASE),
    re.compile(r"new message from (.+?)(?: on \w+|:|$)", re.IGNORECASE),
]
_EMAIL_RE = re.compile(r"<([^>]+)>|^\s*([\w.+-]+@[\w-]+\.[\w.]+)\s*$")
_HANDLE_RE = re.compile(r"@([A-Za-z0-9_.]{2,})")


class IdentityCandidate(BaseModel):
    platform: str
    identity_kind: str  # email | handle
    value_display: str
    value_normalized: str


class ParsedNotification(BaseModel):
    platform: str
    kind: str  # direct_message_notification | platform_activity | direct_email
    actor_candidate: str | None = None
    identity: IdentityCandidate | None = None
    summary: str = ""
    confidence: float
    parser_name: str = PARSER_NAME
    parser_version: str = PARSER_VERSION


def _actor_from_subject(subject: str) -> str | None:
    for pattern in _ACTOR_PATTERNS:
        if match := pattern.search(subject):
            return match.group(1).strip() or None
    return None


def parse_notification(event: InboundEvent) -> ParsedNotification:
    triage = classify(event)
    summary = (event.preview or event.subject)[:200]
    if triage.category == "other_email":
        match = _EMAIL_RE.search(event.sender)
        address = (match.group(1) or match.group(2)) if match else None
        name = event.sender.split("<")[0].strip().strip('"') or None
        identity = None
        if address:
            identity = IdentityCandidate(
                platform="email", identity_kind="email",
                value_display=address, value_normalized=address.strip().lower(),
            )
        return ParsedNotification(
            platform="email", kind="direct_email", actor_candidate=name,
            identity=identity, summary=summary, confidence=triage.confidence,
        )
    platform = event.platform
    if platform is None:
        evidence = f"{event.sender} {event.subject} {event.preview}"
        for name, pattern in _SOCIAL_HINTS.items():
            if pattern.search(evidence):
                platform = name
                break
    kind = ("direct_message_notification"
            if triage.category == "social_message_notification" else "platform_activity")
    identity = None
    if match := _HANDLE_RE.search(f"{event.subject} {event.preview}"):
        handle = match.group(1)
        identity = IdentityCandidate(
            platform=platform or "unknown", identity_kind="handle",
            value_display=f"@{handle}", value_normalized=handle.lower(),
        )
    return ParsedNotification(
        platform=platform or "unknown", kind=kind,
        actor_candidate=_actor_from_subject(event.subject),
        identity=identity, summary=summary, confidence=triage.confidence,
    )
