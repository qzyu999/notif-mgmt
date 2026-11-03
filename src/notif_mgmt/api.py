"""Local HTTP API (A5a read-only; A5b adds mutations).

Thin layer over the existing storage repositories and Pydantic domain models.
No business rules live here beyond HTTP concerns (status codes, filtering).
The app is a single-user local tool: serve it bound to localhost only (e.g.
`uvicorn notif_mgmt.api:app --host 127.0.0.1`). It exposes capped summaries
and sync metadata — never tokens, credentials, or message bodies.

Language note: a signal's platform reflects A3 sender-domain matching against
trusted platform domains, not SPF/DKIM/DMARC authentication of the message.
"""
import os
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from . import storage
from .models import FollowUp, InteractionSignal, Person, PlatformIdentity


class PersonSummary(Person):
    identity_count: int
    platforms: list[str]
    last_interaction_at: str | None = None
    open_followup_count: int


class PersonDetail(BaseModel):
    person: Person
    identities: list[PlatformIdentity]
    signals: list[InteractionSignal]  # newest first
    followups: list[FollowUp]


class TodayResponse(BaseModel):
    due: list[FollowUp]
    snoozed_ready: list[FollowUp]
    review_candidates: list[FollowUp]


class SourceStatus(BaseModel):
    source: str
    account_id: str
    has_cursor: bool
    last_sync_completed_at: str | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    last_recovery_at: str | None = None
    gap_count: int


def create_app(db_path: str | None = None) -> FastAPI:
    path = db_path or os.environ.get("NOTIF_MGMT_DB", "./dev.db")
    app = FastAPI(title="notif-mgmt", version="1")

    def get_db() -> Iterator[sqlite3.Connection]:
        db = storage.connect(path, check_same_thread=False)
        try:
            yield db
        finally:
            db.close()

    Db = Annotated[sqlite3.Connection, Depends(get_db)]

    @app.get("/api/v1/today", response_model=TodayResponse)
    def today(db: Db, now: str | None = None):
        moment = now or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return storage.today_followups(db, moment)

    @app.get("/api/v1/people", response_model=list[PersonSummary])
    def people(db: Db):
        return storage.list_people_with_stats(db)

    @app.get("/api/v1/people/{person_id}", response_model=PersonDetail)
    def person_detail(person_id: int, db: Db):
        person = storage.get_person(db, person_id)
        if person is None:
            raise HTTPException(status_code=404, detail="Unknown person")
        signals = storage.list_signals(db, person_id=person_id)
        return PersonDetail(
            person=person,
            identities=storage.list_identities(db, person_id=person_id),
            signals=list(reversed(signals)),
            followups=storage.list_followups(db, person_id=person_id))

    @app.get("/api/v1/identities", response_model=list[PlatformIdentity])
    def identities(db: Db, match_status: str | None = None):
        return storage.list_identities(db, match_status=match_status)

    @app.get("/api/v1/followups", response_model=list[FollowUp])
    def followups(db: Db, status: str | None = None, kind: str | None = None,
                  person_id: int | None = None):
        return storage.list_followups(db, person_id=person_id, status=status,
                                      kind=kind)

    @app.get("/api/v1/signals", response_model=list[InteractionSignal])
    def signals(db: Db, person_id: int | None = None, status: str | None = None):
        return storage.list_signals(db, person_id=person_id, status=status)

    @app.get("/api/v1/sources", response_model=list[SourceStatus])
    def sources(db: Db):
        return storage.list_sources(db)

    return app


app = create_app()
