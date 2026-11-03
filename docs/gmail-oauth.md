# Gmail configuration — A2 (connector implemented, fake transport verified)

The Gmail connector is implemented and tested entirely against a fake
transport. **No real account has been connected yet.** Live OAuth testing is a
separate, explicitly approved step.

## How it works

- Read-only scope only: `https://www.googleapis.com/auth/gmail.readonly`.
- Initial sync: `users.messages.list` with an explicit query (default
  `newer_than:30d`, override with `--query` or `GMAIL_INITIAL_QUERY`), metadata
  only (From/Subject/snippet), cursor = profile `historyId` captured up front.
- Incremental sync: `users.history.list` from the committed cursor, all pages,
  adds fetched and deduplicated, deletes withdraw the corresponding signals
  (evidence rows are kept).
- Events and cursor commit in **one transaction** per sync; signal derivation
  runs afterwards and self-heals on the next sync if interrupted.
- Expired cursor (HTTP 404): bounded recovery re-imports
  `newer_than:<GMAIL_RECOVERY_DAYS>d` (default 30), records the potential gap
  in `sync_gaps`, and stamps `last_recovery_at`. The gap is visible via
  `notif-mgmt status` — recovery is never presented as lossless.
- 429/5xx are retried with backoff; 401/403 raise an explicit auth error,
  record `last_error_code`, and move nothing.
- Stored excerpts are capped at `NOTIF_MGMT_EXCERPT_CHARS` (default 200).

## Token storage

- **Preferred: macOS Keychain** (via the `security` CLI), service
  `notif-mgmt-gmail`, one item per account email.
- **Fallback: 0600 file** at `NOTIF_MGMT_TOKEN_FILE`
  (default `~/.local/share/notif-mgmt/tokens.json`). Select it with
  `NOTIF_MGMT_TOKEN_STORE=file` (also used automatically off macOS).
- Never commit `credentials.json`, tokens, or databases; never paste OAuth
  secrets into an LLM chat.

## Operator steps (only when live testing is approved)

1. In a Google Cloud project under your control, enable the Gmail API.
2. Configure a consent screen for your own test account, and create an
   installed-desktop OAuth client. Use the least privileged read-only scope.
3. Download the client JSON locally as `credentials.json` (git-ignored), and
   install the optional dependencies: `python -m pip install -e '.[gmail]'`.
4. `notif-mgmt auth` — browser consent once; credentials land in Keychain.
5. `notif-mgmt sync --account <your-email> --query newer_than:30d` — one-shot,
   bounded. Inspect with `notif-mgmt status`, `signals`, and `followups`.
6. Only after verification, schedule repeated `sync` runs (poll interval is an
   external scheduler concern; `GMAIL_POLL_SECONDS=300` is the convention).
7. Understand Google's sensitive/restricted scope verification rules before
   distributing publicly.

References: https://developers.google.com/workspace/gmail/api/guides/sync and
https://developers.google.com/workspace/gmail/api/auth/scopes

## Post-A2 audit fixes (regression-tested, pending local verification run)

An audit of the real (non-fake) code paths found and fixed defects that fake
transport tests could not catch:

- A message deleted between listing and fetch (HTTP 404 on `messages.get`) is
  now skipped instead of crashing the sync or permanently poisoning the
  incremental cursor.
- Gmail quota responses (HTTP 403 with reason `rateLimitExceeded`,
  `userRateLimitExceeded`, or `quotaExceeded`) are retried like 429 instead of
  being misreported as an authentication failure. The real transport now
  extracts the error reason from the API response body.
- Credential refresh failures (`RefreshError`, e.g. a revoked grant) are
  mapped to an authentication error instead of a traceback.
- The user's own SENT and DRAFT messages are no longer ingested as inbound
  interactions during initial or incremental sync.
- CLI `auth` failures (missing client file, denied consent, API error after
  consent) are reported cleanly with exit code 1 instead of a traceback, and
  corrupt stored credentials produce re-auth guidance.
- A corrupt fallback token file raises a clear error, and Keychain save or
  delete failures are no longer silent.

## Exact Google Cloud setup for the live acceptance test

Use a **dedicated test mailbox**, not your primary inbox.

1. Go to the Google Cloud Console and create a project named e.g.
   `notif-mgmt-test`. No billing account is required for the Gmail API at
   this scale.
2. In **APIs & Services → Library**, enable the **Gmail API**.
3. In **APIs & Services → OAuth consent screen**, choose **External**, fill in
   the app name and your contact email, and save. Leave the publishing status
   as **Testing**.
4. Under **Test users**, add the dedicated test mailbox address. While the app
   is in Testing status, only listed test users can authorize, and Google
   expires their refresh tokens after about **7 days**. Re-running
   `notif-mgmt auth` renews access; this is acceptable for the acceptance
   test and must be revisited before any unattended use.
5. In **APIs & Services → Credentials**, choose **Create Credentials → OAuth
   client ID**, application type **Desktop app**, and create it.
6. Download the client JSON and store it **outside the repository**, for
   example at `~/.config/notif-mgmt/credentials.json` with permissions 600.
   Never commit it and never paste its contents into a chat.
7. No scopes need to be pre-registered in the console for this flow. The
   application requests exactly one scope at runtime,
   `https://www.googleapis.com/auth/gmail.readonly`, and the consent screen
   will show read-only access to Gmail.

## Controlled live acceptance procedure (separate local database)

Prerequisites: the setup above is complete, and you have sent three seed
messages to the test mailbox from another account: one ordinary email, one
email with subject `Alex sent you a message on LinkedIn`, and one email you
are willing to delete during the test.

1. Install the Gmail dependencies with
   `python -m pip install -e '.[gmail]'` from the repository root.
2. Set `GMAIL_OAUTH_CLIENT_JSON` to the downloaded client JSON path, or pass
   `--credentials` explicitly.
3. Run `notif-mgmt auth`. A browser opens on `localhost` for Google consent
   (this flow uses PKCE via the Google client library). Confirm the consent
   screen names only read-only Gmail access, approve, and note the account
   email the command prints. Credentials are stored in macOS Keychain under
   the service `notif-mgmt-gmail`.
4. Verify the Keychain item exists **without printing the secret** by running
   `security find-generic-password -a <test-email> -s notif-mgmt-gmail`.
   Do not add `-w`, which would print the credential.
5. Run the first sync against a throwaway database with
   `notif-mgmt sync --account <test-email> --db /tmp/notif-mgmt-smoke.db --query newer_than:7d`.
   Expected result: the command reports fetched and new counts matching the
   seed messages, with the sent-mail exclusion applying to anything you sent
   from the test mailbox itself.
6. Inspect with `notif-mgmt status --db /tmp/notif-mgmt-smoke.db`,
   `notif-mgmt signals --db /tmp/notif-mgmt-smoke.db`, and
   `notif-mgmt followups --db /tmp/notif-mgmt-smoke.db`. The LinkedIn-subject
   seed should appear as a LinkedIn direct-message signal with actor candidate
   Alex and an open review follow-up. Nothing should claim a reply is owed.
7. Run the same sync command again. Expected result: no new items, because
   incremental sync sees no history changes and replay is idempotent.
8. Send one new email to the test mailbox and sync again. Expected result:
   exactly one new signal and one new review candidate.
9. Delete that email in the Gmail web interface and sync again. Expected
   result: the sync reports one deleted item and the corresponding signal
   shows as withdrawn rather than disappearing from history.
10. Rollback at any time by deleting the Keychain item with
    `security delete-generic-password -a <test-email> -s notif-mgmt-gmail`
    and removing `/tmp/notif-mgmt-smoke.db`.

Stop conditions: any consent screen requesting more than read-only Gmail
access, any sync writing to Gmail, any duplicate signals after re-sync, or
any crash. Report the exact output before proceeding.

Polling, external AI inference, and automatic outreach remain disabled. This
procedure is one-shot and manual by design.

## Live acceptance progress

Environment: dedicated test mailbox, OAuth authorized through Step 7, test
database `/tmp/notif-mgmt-smoke.db`, no other database or account involved.

- **Initial bounded sync passed (2026-11-02).** Query window 30 days.
  Result was fetched 7, new 7, duplicates 0, deleted 0, recovered false.
  All three synthetic seed messages were imported, including the
  LinkedIn-style notification from Alex. Seven interaction signals and seven
  review/open follow-up candidates were created. Sync state showed cursor
  2281, last_error None, gaps 0.
- **Incremental idempotency passed.** An immediate second sync reported
  fetched 0, new 0, duplicates 0, deleted 0, recovered false. The cursor
  remained 2281, all seven review candidates were unchanged, and no errors or
  recovery gaps were recorded.
- **New-message incremental ingestion passed.** A second sync after new mail
  arrived reported fetched 2, new 2, duplicates 0, deleted 0, recovered
  false. The cursor advanced from 2281 to 2464 and signals increased from 7
  to 9. One imported item was the new `A2 smoke incremental` test email and
  the other was an additional Google notification, which accounts for the
  second new message. last_error remained None and gaps remained 0.
- **Trash-no-withdrawal passed.** After the `A2 smoke delete me` message was
  moved to Trash, sync reported fetched 0, new 0, duplicates 0, deleted 0,
  recovered false. A direct database check confirmed its signal (id 1)
  remained `active`, so a label change was not misread as deletion.
- **Permanent-delete-withdrawal passed.** After `A2 smoke delete me` was
  permanently deleted from Trash, sync reported fetched 0, new 0,
  duplicates 0, deleted 1, recovered false. Its signal (id 1) is now
  `withdrawn`; all other signals remain `active`. The signal row still joins
  to its `inbound_events` evidence row, proving the historical evidence was
  preserved and only the inferred signal state changed.

**A2 live acceptance is complete for the dedicated test mailbox**: bounded
initial sync, incremental idempotency, new-message ingestion, Trash treated as
a label change, and permanent deletion treated as signal withdrawal all behave
as specified against the real Gmail API, read-only, with no polling and no
external inference. Live OAuth remains limited to the test account; any use
beyond it requires a separate decision.
