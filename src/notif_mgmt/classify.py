"""Explainable, conservative heuristics. NOT a claim to know if someone needs a reply."""
import re

from .models import InboundEvent, TriageResult


_SOCIAL_HINTS = {
    "linkedin": re.compile(r"linkedin", re.I),
    "x": re.compile(r"(?<!\w)(?:twitter|x\.com)(?!\w)", re.I),
    "reddit": re.compile(r"reddit", re.I),
    "instagram": re.compile(r"instagram", re.I),
    "xiaohongshu": re.compile(r"xiaohongshu|小红书|rednote", re.I),
}

_DIRECT_MESSAGE_HINT = re.compile(
    r"(?:sent you a message|new message from|messaged you|sent you a direct message|"
    r"you have a new message|has sent you a message)", re.I
)



def classify(event: InboundEvent) -> TriageResult:
    evidence = " ".join([event.sender, event.subject, event.preview])
    platform = event.platform
    if platform is None:
        for name, pattern in _SOCIAL_HINTS.items():
            if pattern.search(evidence):
                platform = name
                break
    if platform and _DIRECT_MESSAGE_HINT.search(evidence):
        return TriageResult(
            category="social_message_notification", priority="medium", state="needs_review",
            reason=f"Possible inbound {platform} message; notification cannot establish reply status",
            confidence=0.9,
        )
    if platform:
        return TriageResult(
            category="social_other_notification", priority="low", state="needs_review",
            reason=f"{platform} activity; message type or action unknown", confidence=0.7,
        )
    return TriageResult(
        category="other_email", priority="low", state="needs_review",
        reason="Unclassified; human or LLM review required", confidence=0.4,
    )
