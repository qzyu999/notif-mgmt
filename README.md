# notif-mgmt

Local-first AI relationship and notification manager. Its first ingestion source is Gmail; future sources include macOS/iPhone notifications and authorized APIs or exports. **No unattended outreach.**

## Project status

This is a small, testable Python starter scaffold, **not yet a connected Gmail application**. It includes a SQLite store, deterministic notification classification, sample events, tests, architectural requirements and an implementation prompt for an AI coding agent.

## Goals

- Maintain one source-of-truth for contacts, external identities, conversations, incoming notification events, follow-up actions, and sync cursors.
- Gmail read-only OAuth: initial user-selected history import, then incremental sync every five minutes using Gmail `history.list` and message IDs.
- Prioritize deterministic extraction for standardized social notification emails; run LLM inference only for relevant ambiguous cases with explicit consent.
- Support `needs_review`, `needs_reply`, `waiting_on_them`, `follow_up`, `resolved`, `ignored` workflow states. A notification alone must **not** be interpreted as proof that a response is owed or that someone hasn't been answered.
- Enable local, exportable, provider-independent data storage. No platform scraping or automated replies in MVP.

## Quick start (local, no Gmail needed)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
notif-mgmt demo --db ./dev.db
notif-mgmt list --db ./dev.db
```

The demo inserts **synthetic** notifications from `fixtures/sample-notifications.json` and classifies them; it's safe to run offline.

## Roadmap

1. **Foundation (starter scaffold):** schema, idempotent import, rule-based classification, fixtures/tests.
2. **Gmail connector:** single-user local OAuth, `gmail.readonly`, initial scoped backfill, 5-minute incremental sync, `historyId` persistence, 404 resync recovery, rate limits, errors, zero duplicate actions.
3. **AI classifier:** opt-in Meta Model API adapter; typed JSON schema, confidence, evidence/provenance, safeguards for private message content, budget caps, rule-only/local fallback.
4. **Dashboard:** local-only UI for contacts, inbox candidates, triage, follow-ups, audit trail, manual status edits; no auto-send.
5. **Notification connector:** assess iPhone-to-Mac mirroring capture reliability and permissions before making promises about full coverage.

## Security and data ownership

- Repo should be **private** while experimenting with personal email data. Never commit OAuth secrets, access/refresh tokens, mailbox contents, exported conversations, `*.db`, or API keys.
- Only read messages authorized by the owner; redact sensitive fields before external LLM calls and require explicit user opt-in.
- Store raw bodies only if necessary and explicitly enabled. Keep user-level DB in a restricted local directory. This starter uses SQLite without disk encryption; protect data with OS-level encryption or add SQLCipher for sensitive use.
- Keep an auditable import log, track Gmail message IDs, and offer data export/delete.
- This does not bypass platform access restrictions; it only processes messages and notifications legitimately delivered to the user.

## Agent instructions

See [`AGENTS.md`](AGENTS.md), [`docs/architecture.md`](docs/architecture.md), and [`prompts/meta-coding-agent.md`](prompts/meta-coding-agent.md).

## GitHub

Create a **private** empty repository named `notif-mgmt` under `qzyu999`, without adding README or `.gitignore`, then from the extracted directory:

```bash
git init -b main
git add .
git commit -m "chore: initialize local-first notification CRM"
git remote add origin git@github.com:qzyu999/notif-mgmt.git
git push -u origin main
```
