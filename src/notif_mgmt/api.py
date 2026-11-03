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
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

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


class PersonCreate(BaseModel):
    display_name: str = Field(min_length=1)
    kind: str = "person"
    notes: str = ""


class IdentityCreate(BaseModel):
    platform: str = Field(min_length=1)
    identity_kind: str = Field(min_length=1)
    value: str = Field(min_length=1)


class PersonRef(BaseModel):
    person_id: int


class FollowUpUpdate(BaseModel):
    status: str | None = None
    kind: str | None = None
    note: str | None = None
    due_at: str | None = None
    snoozed_until: str | None = None


_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _hostname(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("["):
        return host[1:].split("]", 1)[0]
    return host.rsplit(":", 1)[0] if ":" in host else host


def _storage_error(error: ValueError) -> HTTPException:
    message = str(error)
    if message.startswith("Unknown"):
        return HTTPException(status_code=404, detail=message)
    if "already linked" in message or "already owned" in message:
        return HTTPException(status_code=409, detail=message)
    return HTTPException(status_code=422, detail=message)


def create_app(db_path: str | None = None,
               allowed_hosts: frozenset[str] = frozenset(_LOCAL_HOSTS)) -> FastAPI:
    path = db_path or os.environ.get("NOTIF_MGMT_DB", "./dev.db")
    app = FastAPI(title="notif-mgmt", version="1")

    @app.middleware("http")
    async def local_mutation_guard(request: Request, call_next):
        # CORS alone is not a boundary: mutations require a localhost Host,
        # and a localhost Origin when the browser sends one (DNS-rebinding
        # and cross-site form/fetch protection for the local app).
        if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            if _hostname(request.headers.get("host", "")) not in allowed_hosts:
                return JSONResponse({"detail": "Mutations are localhost-only"},
                                    status_code=403)
            origin = request.headers.get("origin")
            if origin and urlparse(origin).hostname not in allowed_hosts:
                return JSONResponse({"detail": "Foreign Origin rejected"},
                                    status_code=403)
        return await call_next(request)

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

    @app.post("/api/v1/people", response_model=Person, status_code=201)
    def create_person(body: PersonCreate, db: Db):
        return storage.create_person(db, body.display_name, kind=body.kind,
                                     notes=body.notes)

    @app.post("/api/v1/people/{person_id}/identities",
              response_model=PlatformIdentity, status_code=201)
    def add_identity(person_id: int, body: IdentityCreate, db: Db):
        if storage.get_person(db, person_id) is None:
            raise HTTPException(status_code=404, detail="Unknown person")
        try:
            return storage.add_identity(db, person_id, platform=body.platform,
                                        identity_kind=body.identity_kind,
                                        value=body.value)
        except ValueError as error:
            raise _storage_error(error) from error

    @app.post("/api/v1/identities/{identity_id}/link",
              response_model=PlatformIdentity)
    def link_identity(identity_id: int, body: PersonRef, db: Db):
        identity = storage.get_identity(db, identity_id)
        if identity is None or storage.get_person(db, body.person_id) is None:
            raise HTTPException(status_code=404, detail="Unknown identity or person")
        if identity.person_id not in (None, body.person_id):
            raise HTTPException(
                status_code=409, detail="Identity already linked to another person")
        storage.link_identity(db, identity_id, body.person_id)
        return storage.get_identity(db, identity_id)

    @app.post("/api/v1/signals/{signal_id}/assign",
              response_model=InteractionSignal)
    def assign_signal(signal_id: int, body: PersonRef, db: Db):
        try:
            storage.assign_signal_person(db, signal_id, body.person_id)
        except ValueError as error:
            raise _storage_error(error) from error
        row = next((s for s in storage.list_signals(db) if s.id == signal_id), None)
        return row

    @app.patch("/api/v1/followups/{followup_id}", response_model=FollowUp)
    def update_followup(followup_id: int, body: FollowUpUpdate, db: Db):
        changes: dict = {"status": body.status, "kind": body.kind,
                         "note": body.note}
        if "due_at" in body.model_fields_set:
            changes["due_at"] = body.due_at
        if "snoozed_until" in body.model_fields_set:
            changes["snoozed_until"] = body.snoozed_until
        try:
            return storage.update_followup(db, followup_id, **changes)
        except ValueError as error:
            raise _storage_error(error) from error

    return app


app = create_app()
