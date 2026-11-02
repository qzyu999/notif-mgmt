# notif-mgmt

Local-first AI relationship and notification manager. Its first ingestion source is Gmail; future sources include macOS/iPhone notifications and authorized APIs or exports. **No unattended outreach.**

## Project status

Phase A (functionality first). **M0 + A1 implemented and verified (2026-11-02):** versioned SQLite schema (v2), the canonical **Person → Platform Identities → Interaction Signals → Follow-ups** model, deterministic parsing of synthetic Gmail notification fixtures into interaction signals and review candidates, and minimal identity resolution (unresolved identities, exact email/handle matching, manual linking). **Evidence:** `pytest` 17 passed, `ruff check src tests` clean; CLI demo on a temp DB inserted 3 signals + 3 review candidates, and a replay inserted 0 (idempotent). **A2 implemented and verified against a fake Gmail transport (2026-11-02):** schema v3 with account-scoped source events, Keychain/0600 token stores, incremental sync with transactional cursor, bounded expired-cursor recovery with recorded sync gaps, excerpt cap (37 tests passed total). No real Gmail account has been connected yet; LLM enrichment (A4) and the web UI (A5) are not started. No elaborate visual design until Phase B.

## Goals

- Answer three questions: who reached out, what is my relationship with them across platforms, and do I need to respond/follow up?
- Maintain one source-of-truth for **people/entities, platform identities, interaction signals (deduplicated interpretations of source evidence), follow-up actions, and sync cursors**. Source evidence is stored separately from inferred state.
- Gmail read-only OAuth: initial user-selected history import, then incremental sync every five minutes using Gmail `history.list` and message IDs.
- Prioritize deterministic extraction for standardized social notification emails; run LLM inference only for relevant ambiguous cases with explicit consent.
- Follow-ups have a kind (`review`, `reply`, `waiting`, `follow_up`) and a workflow state (`open`, `snoozed`, `done`, `dismissed`). A notification alone must **not** be interpreted as proof that a response is owed or that someone hasn't been answered; it creates at most a `review` candidate.
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

The demo inserts **synthetic** notifications from `fixtures/sample-notifications.json`, derives interaction signals, and creates review candidates; it's safe to run offline and idempotent on replay.

```bash
notif-mgmt demo --db ./dev.db       # fixture events -> signals -> review candidates
notif-mgmt signals --db ./dev.db
notif-mgmt followups --db ./dev.db  # open review queue (alias: today)
notif-mgmt add-person --db ./dev.db --name "Alex"
notif-mgmt assign-signal --db ./dev.db --signal 1 --person 1
notif-mgmt people --db ./dev.db
```

## Roadmap

Phase A — working product (vertical slices, functionality first):

1. **M0/A1 (done):** spec reset; canonical people/identities/signals/follow-ups schema with versioned migrations; deterministic fixture pipeline; minimal identity resolution (unresolved, exact match, manual link — no name-only merging, no merge workflows yet); CLI views.
2. **A2 — Gmail connector (done, fake transport; live OAuth pending approval):** single-user local OAuth, `gmail.readonly`, initial scoped backfill, incremental sync, `historyId` persistence, 404 bounded recovery with recorded gaps, rate limits, errors, zero duplicate actions. All network access behind a fakeable transport; Keychain token storage with 0600 fallback.
3. **A3 — Parser registry:** versioned deterministic parsers (LinkedIn/X/Reddit/Instagram/Xiaohongshu/direct email) with a precision/recall fixture corpus.
4. **A4 — Optional AI classifier:** opt-in Meta Muse adapter behind a vendor-neutral interface; typed JSON schema, confidence, evidence/provenance, safeguards for private message content, budget caps, rule-only/local fallback. Disabled by default.
5. **A5 — Minimal web app:** FastAPI + React/TypeScript/Vite with Today, People, Follow-ups, and Sources views; semantic design tokens, accessible/responsive, no elaborate styling yet.
6. **A6 — End-to-end integration:** fixture-based failure/recovery suite (first/resumed sync, duplicates, crashes, deletions, cursor recovery).

Phase B — deliberate UI/UX design exploration, only after the core workflows are functional.

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
