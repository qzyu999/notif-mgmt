from dataclasses import dataclass

from pydantic import BaseModel


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
    account_id: str = "default"  # owning account/mailbox; scopes (source, external_id)


@dataclass(frozen=True)
class TriageResult:
    category: str
    priority: str
    state: str
    reason: str
    confidence: float


# --- Canonical person-centric domain (A1) -------------------------------------
# DB-row models. Person/identity/signal/follow-up state is inferred or
# user-confirmed state and is kept separate from raw source evidence.


class Person(BaseModel):
    id: int
    kind: str = "person"  # person | organization | unknown
    display_name: str
    notes: str = ""
    created_at: str
    updated_at: str


class PlatformIdentity(BaseModel):
    id: int
    person_id: int | None = None
    platform: str
    identity_kind: str  # email | handle | profile | other
    value_normalized: str
    value_display: str
    match_status: str = "unmatched"  # unmatched | suggested | verified | rejected
    match_method: str | None = None  # parser | exact | manual
    confidence: float | None = None
    created_at: str
    updated_at: str


class InteractionSignal(BaseModel):
    id: int
    source_event_id: int
    identity_id: int | None = None
    person_id: int | None = None
    platform: str
    kind: str
    occurred_at: str
    summary: str = ""
    actor_candidate: str | None = None  # display name only; NOT an identity
    confidence: float
    parser_name: str
    parser_version: str
    dedupe_key: str
    status: str = "active"  # active | withdrawn
    created_at: str


class FollowUp(BaseModel):
    id: int
    person_id: int | None = None
    signal_id: int | None = None
    kind: str = "review"  # review | reply | waiting | follow_up
    status: str = "open"  # open | snoozed | done | dismissed
    title: str
    note: str = ""
    due_at: str | None = None
    snoozed_until: str | None = None
    created_by: str = "rule"  # rule | llm | user
    confidence: float | None = None
    created_at: str
    updated_at: str
    resolved_at: str | None = None
