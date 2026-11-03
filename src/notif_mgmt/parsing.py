"""Deterministic parsing of notification evidence into interaction candidates.

A3: platform origin must be *proven* by sender-domain evidence. Wording that
merely mentions a platform is never treated as proof of origin, and actor
candidates / handle identities are extracted only from verified platform
notifications. A display name alone is NEVER an identity. Automated and
unclassified mail still becomes a signal (evidence is preserved), but it
carries no actor, no identity, and no review follow-up downstream.
"""
import re
from dataclasses import dataclass

from pydantic import BaseModel

from .classify import _SOCIAL_HINTS
from .config import excerpt_chars
from .models import InboundEvent

PARSER_NAME = "generic-email"
PARSER_VERSION = "2"


@dataclass(frozen=True)
class PlatformSpec:
    platform: str
    domains: tuple[str, ...]

    @property
    def parser_name(self) -> str:
        return f"{self.platform}-notifications"


PLATFORM_SPECS = (
    PlatformSpec("linkedin", ("linkedin.com",)),
    PlatformSpec("x", ("twitter.com", "x.com")),
    PlatformSpec("reddit", ("reddit.com",)),
    PlatformSpec("instagram", ("instagram.com", "facebookmail.com")),
    PlatformSpec("xiaohongshu", ("xiaohongshu.com", "rednote.com")),
)

PARSER_REGISTRY: dict[str, str] = {
    **{spec.parser_name: "1" for spec in PLATFORM_SPECS},
    PARSER_NAME: PARSER_VERSION,
}

_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_PAREN_HANDLE_RE = re.compile(r"^(.+?)\s*\(@([A-Za-z0-9_.]+)\)")
_REDDIT_USER_RE = re.compile(r"\bu/([A-Za-z0-9_-]+)")
_CHINESE_DM_RE = re.compile(r"^(.+?)\s*给你发了一条消息")
_ACTOR_PATTERNS = [
    re.compile(r"^(.+?) sent you an invitation", re.IGNORECASE),
    re.compile(r"^(.+?) sent you a (?:direct )?message", re.IGNORECASE),
    re.compile(r"^(.+?) messaged you", re.IGNORECASE),
    re.compile(r"^(.+?) has sent you a message", re.IGNORECASE),
    re.compile(r"^(.+?) mentioned you", re.IGNORECASE),
    re.compile(r"new message from (.+?)(?: on \w+|:|$)", re.IGNORECASE),
]
_DM_PATTERNS = [
    re.compile(r"sent you a (?:direct )?message", re.IGNORECASE),
    re.compile(r"messaged you", re.IGNORECASE),
    re.compile(r"has sent you a message", re.IGNORECASE),
    re.compile(r"new (?:chat )?message from", re.IGNORECASE),
    re.compile(r"you have a new message", re.IGNORECASE),
    re.compile(r"给你发了一条消息"),
]
_AUTOMATED_LOCALPARTS = {
    "noreply", "donotreply", "notifications", "notification",
    "mailerdaemon", "newsletter", "newsletters", "digest",
    "promotions", "promo", "marketing",
}
_NON_ACTORS = {"someone", "a user", "you"}


class IdentityCandidate(BaseModel):
    platform: str
    identity_kind: str  # email | handle
    value_display: str
    value_normalized: str


class ParsedNotification(BaseModel):
    platform: str
    kind: str  # direct_message_notification | platform_activity | direct_email
    #            | automated_notification | unclassified_email
    actor_candidate: str | None = None
    identity: IdentityCandidate | None = None
    summary: str = ""
    confidence: float
    parser_name: str = PARSER_NAME
    parser_version: str = PARSER_VERSION


def _sender_parts(sender: str) -> tuple[str, str | None]:
    match = _EMAIL_RE.search(sender)
    if not match:
        return sender.strip(), None
    address = match.group(1)
    display = sender[:match.start()].replace("<", " ").strip().strip('"').strip()
    return display, address


def _verified_spec(address: str | None) -> PlatformSpec | None:
    if not address:
        return None
    domain = address.rsplit("@", 1)[1].lower().rstrip(".")
    for spec in PLATFORM_SPECS:
        if any(domain == trusted or domain.endswith(f".{trusted}")
               for trusted in spec.domains):
            return spec
    return None


def _clean_actor(raw: str | None) -> str | None:
    actor = (raw or "").strip().strip('"') or None
    if actor is None or actor.lower() in _NON_ACTORS:
        return None
    return actor


def _extract_actor_and_handle(spec: PlatformSpec, subject: str):
    """Conservative extraction, verified platform mail only."""
    if match := _PAREN_HANDLE_RE.search(subject):
        handle = match.group(2)
        identity = IdentityCandidate(
            platform=spec.platform, identity_kind="handle",
            value_display=f"@{handle}", value_normalized=handle.lower())
        return _clean_actor(match.group(1)), identity
    if match := _REDDIT_USER_RE.search(subject):
        handle = match.group(1)
        identity = IdentityCandidate(
            platform=spec.platform, identity_kind="handle",
            value_display=f"u/{handle}", value_normalized=handle.lower())
        return handle, identity
    if match := _CHINESE_DM_RE.search(subject):
        return _clean_actor(match.group(1)), None
    for pattern in _ACTOR_PATTERNS:
        if match := pattern.search(subject):
            return _clean_actor(match.group(1)), None
    return None, None


def parse_notification(event: InboundEvent) -> ParsedNotification:
    summary = (event.preview or event.subject)[:excerpt_chars()]
    display, address = _sender_parts(event.sender)

    spec = _verified_spec(address)
    if spec is not None:
        kind = ("direct_message_notification"
                if any(p.search(event.subject) for p in _DM_PATTERNS)
                else "platform_activity")
        actor, identity = _extract_actor_and_handle(spec, event.subject)
        return ParsedNotification(
            platform=spec.platform, kind=kind, actor_candidate=actor,
            identity=identity, summary=summary,
            confidence=0.9 if kind == "direct_message_notification" else 0.7,
            parser_name=spec.parser_name,
            parser_version=PARSER_REGISTRY[spec.parser_name])

    # A sender that *claims* a platform in its own name/address without a
    # verified domain is not evidence of that platform (e.g. lookalike or
    # phishing senders). Never extract an actor or identity from it.
    if any(pattern.search(event.sender) for pattern in _SOCIAL_HINTS.values()):
        return ParsedNotification(
            platform="unknown", kind="unclassified_email", summary=summary,
            confidence=0.3)

    if address:
        localpart = re.sub(r"[-_.]", "", address.split("@", 1)[0].lower())
        if localpart in _AUTOMATED_LOCALPARTS:
            return ParsedNotification(
                platform="unknown", kind="automated_notification",
                summary=summary, confidence=0.8)
        identity = IdentityCandidate(
            platform="email", identity_kind="email",
            value_display=address, value_normalized=address.strip().lower())
        return ParsedNotification(
            platform="email", kind="direct_email",
            actor_candidate=display or None, identity=identity,
            summary=summary, confidence=0.6)

    return ParsedNotification(
        platform="unknown", kind="unclassified_email", summary=summary,
        confidence=0.3)
