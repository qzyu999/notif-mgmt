"""Gmail connector (A2): read-only, incremental, idempotent.

All network access goes through a transport object. Tests use a deterministic
fake; the real Gmail API transport is built lazily (google client libraries
are an optional dependency) and is never constructed in tests.

Invariants: the sync cursor advances only in the same transaction as the
events it covers; an expired history cursor triggers bounded recovery with an
explicitly recorded sync gap; auth failures are explicit and move nothing.
"""
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from .models import InboundEvent
from .pipeline import process_unprocessed_events
from .storage import (
    commit_events_and_cursor,
    commit_sync_batch,
    get_sync_state,
    record_sync_error,
    record_sync_gap,
)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
SOURCE = "gmail"


class GmailApiError(Exception):
    """Transport-level Gmail API failure with an HTTP status."""

    def __init__(self, status, message="", reason=None):
        super().__init__(message or f"Gmail API error {status}")
        self.status = status
        self.reason = reason


_QUOTA_REASONS = {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded"}


class GmailAuthError(Exception):
    """401/403: credentials missing, expired, or revoked. Reauth required."""


class GmailSyncError(Exception):
    """Sync failed without advancing the cursor."""


class GmailTransport(Protocol):
    def get_profile(self) -> dict: ...
    def list_message_ids(self, query: str, page_token: str | None = None) -> dict: ...
    def list_history(self, start_history_id: str,
                     page_token: str | None = None) -> dict: ...
    def get_message(self, message_id: str) -> dict: ...


@dataclass(frozen=True)
class SyncResult:
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    deleted: int = 0
    recovered: bool = False


def _iso_from_ms(ms: str) -> str:
    return datetime.fromtimestamp(int(ms) / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class GmailConnector:
    def __init__(self, db, transport: GmailTransport, *, account_id: str,
                 sleeper=time.sleep, max_retries: int = 3, recovery_days: int = 30):
        self.db = db
        self.transport = transport
        self.account_id = account_id
        self.sleeper = sleeper
        self.max_retries = max_retries
        self.recovery_days = recovery_days

    # -- transport calls with retry / error mapping --------------------------
    def _call(self, fn, *args):
        attempt = 0
        while True:
            try:
                return fn(*args)
            except GmailApiError as error:
                quota = error.status == 429 or (
                    error.status == 403 and error.reason in _QUOTA_REASONS)
                if error.status == 401 or (error.status == 403 and not quota):
                    raise GmailAuthError(
                        f"Gmail authorization failed (HTTP {error.status}); "
                        "reauthentication required") from error
                if error.status == 404:
                    raise  # callers decide (expired history cursor or deleted message)
                retryable = quota or error.status in (500, 502, 503, 504)
                if retryable and attempt < self.max_retries:
                    self.sleeper(min(2 ** attempt, 8))
                    attempt += 1
                    continue
                raise GmailSyncError(f"Gmail request failed: {error}") from error

    def _fail(self, error: Exception) -> Exception:
        status = error.status if isinstance(error, GmailApiError) else None
        if isinstance(error, GmailAuthError):
            status = 401
        record_sync_error(self.db, SOURCE, self.account_id,
                          str(status) if status else type(error).__name__, str(error))
        return error

    # -- conversion ------------------------------------------------------------
    def _to_event(self, raw: dict) -> InboundEvent:
        headers = {h["name"].lower(): h["value"]
                   for h in raw.get("payload", {}).get("headers", [])}
        return InboundEvent(
            source=SOURCE, external_id=raw["id"],
            sender=headers.get("from", ""), subject=headers.get("subject", ""),
            preview=raw.get("snippet", ""), received_at=_iso_from_ms(raw["internalDate"]),
            thread_id=raw.get("threadId"),
            conversation_url=f"https://mail.google.com/mail/u/0/#inbox/{raw['id']}",
            account_id=self.account_id)

    def _fetch_events(self, message_ids):
        events = []
        for mid in message_ids:
            try:
                raw = self._call(self.transport.get_message, mid)
            except GmailApiError as error:
                if error.status == 404:
                    continue  # deleted between listing and fetch; not an error
                raise
            labels = set(raw.get("labelIds") or [])
            if labels & {"SENT", "DRAFT"}:
                continue  # the user's own mail is not an inbound interaction
            events.append(self._to_event(raw))
        return events

    def _list_all_ids(self, query: str) -> list[str]:
        ids, token = [], None
        while True:
            page = self._call(self.transport.list_message_ids, query, token)
            ids.extend(m["id"] for m in page.get("messages", []))
            token = page.get("nextPageToken")
            if not token:
                return ids

    # -- sync operations ---------------------------------------------------------
    def sync_initial(self, *, query: str) -> SyncResult:
        """Bounded first sync. Cursor = profile historyId captured up front;
        overlap with the first incremental sync replays idempotently."""
        try:
            return self._initial(query=query, recovered=False, old_cursor=None)
        except (GmailAuthError, GmailSyncError) as error:
            raise self._fail(error)

    def _initial(self, *, query: str, recovered: bool, old_cursor: str | None) -> SyncResult:
        profile = self._call(self.transport.get_profile)
        new_cursor = profile["historyId"]
        ids = self._list_all_ids(query)
        events = self._fetch_events(ids)
        inserted = commit_events_and_cursor(
            self.db, SOURCE, events, new_cursor, account_id=self.account_id)
        if recovered:
            record_sync_gap(self.db, SOURCE, self.account_id, old_cursor,
                            new_cursor, query)
        process_unprocessed_events(self.db, source=SOURCE, account_id=self.account_id)
        return SyncResult(fetched=len(events), inserted=inserted,
                          duplicates=len(events) - inserted, recovered=recovered)

    def sync_incremental(self) -> SyncResult:
        state = get_sync_state(self.db, SOURCE, self.account_id)
        if state is None or not state["cursor"]:
            raise GmailSyncError("No initial sync for this account; run sync_initial first")
        cursor = state["cursor"]
        try:
            added_ids, deleted_ids, new_cursor = [], [], cursor
            token = None
            while True:
                page = self._call(self.transport.list_history, cursor, token)
                for change in page.get("history", []):
                    added_ids.extend(m["message"]["id"]
                                     for m in change.get("messagesAdded", []))
                    deleted_ids.extend(m["message"]["id"]
                                       for m in change.get("messagesDeleted", []))
                new_cursor = page.get("historyId", new_cursor)
                token = page.get("nextPageToken")
                if not token:
                    break
        except GmailApiError as error:
            if error.status != 404:
                raise self._fail(error)
            # Expired cursor: bounded recovery, gap recorded explicitly.
            query = f"newer_than:{self.recovery_days}d"
            try:
                return self._initial(query=query, recovered=True, old_cursor=cursor)
            except (GmailAuthError, GmailSyncError) as recovery_error:
                raise self._fail(recovery_error)
        except (GmailAuthError, GmailSyncError) as error:
            raise self._fail(error)
        # Repair signals missing from an earlier committed batch before this
        # batch applies deletions. Otherwise a message deleted while its
        # signal was still underived would be recreated as active below.
        process_unprocessed_events(self.db, source=SOURCE, account_id=self.account_id)
        try:
            events = self._fetch_events(added_ids)
            inserted, deleted = commit_sync_batch(
                self.db, SOURCE, events, new_cursor, account_id=self.account_id,
                deleted_external_ids=deleted_ids)
        except (GmailAuthError, GmailSyncError) as error:
            raise self._fail(error)
        process_unprocessed_events(self.db, source=SOURCE, account_id=self.account_id)
        return SyncResult(fetched=len(events), inserted=inserted,
                          duplicates=len(events) - inserted, deleted=deleted)


# -- real-account wiring (lazy; never imported by tests) ----------------------

def build_api_transport(credentials_json: str):
    """Construct the real Gmail API transport from stored credentials JSON."""
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    class _Transport:
        def __init__(self):
            creds = Credentials.from_authorized_user_info(
                json.loads(credentials_json), SCOPES)
            self.service = build("gmail", "v1", credentials=creds)

        def _execute(self, request):
            try:
                return request.execute()
            except RefreshError as error:
                # A revoked or expired grant must surface as an auth failure
                # the connector understands, not as a traceback.
                raise GmailApiError(401, f"credentials refresh failed {error}") from error
            except HttpError as error:
                reason = None
                try:
                    payload = json.loads(error.content or b"{}")
                    reason = payload["error"]["errors"][0].get("reason")
                except (ValueError, KeyError, IndexError, TypeError):
                    reason = None
                raise GmailApiError(error.resp.status, str(error), reason=reason) from error

        def get_profile(self):
            return self._execute(self.service.users().getProfile(userId="me"))

        def list_message_ids(self, query, page_token=None):
            return self._execute(self.service.users().messages().list(
                userId="me", q=query, pageToken=page_token))

        def list_history(self, start_history_id, page_token=None):
            return self._execute(self.service.users().history().list(
                userId="me", startHistoryId=start_history_id, pageToken=page_token))

        def get_message(self, message_id):
            return self._execute(self.service.users().messages().get(
                userId="me", id=message_id, format="metadata",
                metadataHeaders=["From", "Subject", "Date"]))

    return _Transport()


def authorize(token_store, credentials_path: str) -> str:
    """Interactive read-only OAuth; saves credentials JSON under the account
    email in the token store. Returns the account email."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    creds = flow.run_local_server(port=0)
    transport = build_api_transport(creds.to_json())
    account = transport.get_profile()["emailAddress"]
    token_store.save(account, creds.to_json())
    return account
