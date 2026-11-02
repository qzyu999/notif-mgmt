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
