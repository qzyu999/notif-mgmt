from dataclasses import dataclass


@dataclass(frozen=True)
class InboundEvent:
    source: str
    external_id: str
    sender: str
    subject: str
    preview: str
    received_at: str  # ISO 8601 UTC; ingestion adapters must normalize timestamps.
    platform: str | None = None
    thread_id: str | None = None
    conversation_url: str | None = None


@dataclass(frozen=True)
class TriageResult:
    category: str
    priority: str
    state: str
    reason: str
    confidence: float
