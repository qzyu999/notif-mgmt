# Copy/paste prompt — coding agent using Meta hackathon credits

> **Superseded (2026-11-02, M0):** the canonical specs are now `README.md`, `AGENTS.md`, `docs/architecture.md`, and `docs/decisions.md` (person-centric model; A1 foundation implemented). This prompt is kept for historical context; milestone numbering below (M1–M7) predates the A1–A6 plan.

You are the principal engineer implementing `qzyu999/notif-mgmt`, a PRIVATE, local-first AI CRM that consolidates founder relationship signals from Gmail notification emails first, then later from macOS-mirrored iPhone notifications. The objective is to answer: "Who contacted me? About what? Who might need a follow-up? When did we last interact?" The initial use case is coordinating developer, GPU-provider, tester, investor, and collaborator conversations for a project called Inference Exchange. This is a distinct repo, not part of Inference Exchange.

Read `README.md`, `AGENTS.md`, `docs/architecture.md`, `docs/decisions.md` and the entire code/test tree BEFORE modifying code. Preserve the invariants and work via small, tested vertical slices. Do not replace the existing implementation wholesale.

## Engineering stack

Python 3.11+, SQLite, Gmail API and local OAuth for one consenting user, deterministic pytest fixtures with mocked external services, FastAPI only when needed for local UI, React/Vite only after the Gmail CLI works. Use incremental Gmail history synchronization every 300 seconds. Do NOT repeatedly scan the whole mailbox. Keep the model integration vendor-neutral behind an adapter. The Meta hackathon gave me Model API credits; do not invent endpoint URLs or model identifiers. Read the real provider docs and use configured `LLM_BASE_URL`, `LLM_MODEL`, `META_API_KEY` (or their documented equivalents). Ask for configuration only when actually required. Never log API keys. Offer rule-only mode if the Meta API is not configured.

## Non-negotiable privacy and correctness

- Gmail: read-only OAuth scope; minimal permissions; initial user-selected query and date range. No sending, deleting, modifying or marking email as read.
- Local-first: personal database not committed to GitHub, no PII in test fixtures or telemetry, explicit opt-in before sending sensitive message content to a remote LLM. Prefer extracted/redacted snippets and permit fully local/no-LLM mode.
- A social notification is evidence of *possible* communication, NOT proof the user owes a reply. Represent uncertainty and provide links back to original messages where available.
- No browser automation, private social-media APIs, scraping or automated outreach in this release.
- Avoid contact-identity conflation. Never automatically merge people based on common display names; allow reversible manual merges with provenance.
- Duplicate Gmail history events and job retries must not create duplicate records or tasks. All cursors must be transactionally updated with ingested events; handle expired Gmail historyId (404), pagination, auth expiry, rate limits, crash/restart and backfills.

## Build milestones in order

M1 — Foundation tests and schema: audit provided scaffold; add explicit account/source namespace, normalized source-event schema, dedupe/upsert semantics, migration/versioning, deterministic sample emails, and time/date boundaries. Add tests first.

M2 — Gmail OAuth and initial importer: interactive local OAuth login, read-only access, scoped historical backfill (start with 30 days). Fetch message IDs and selectively fetch headers/snippets; do not retain full body by default. Build a CLI with `auth`, `sync --once`, `sync --watch`, `status` and `replay-fixtures`. All network calls must have fakes for tests.

M3 — Incremental sync: `users.history.list`, pagination, last successful historyId, repeatable 5-minute polling and controlled recovery after expired cursors; emit clear counters: fetched, new, duplicate, failed. Write integration tests for initial/resumed sync, overlapping history, crash during batch, 404, 429 and auth revocation.

M4 — Deterministic parsers: configurable registry for LinkedIn/X/Reddit/social notification templates using sender+subject+body snippets. Version rules and maintain precision/recall fixture set. Unknown templates degrade to review queue; never fabricate full messages or response status.

M5 — Meta Model API intelligence: optional adapter for relevance classification, person/organization extraction, prospective relationship type (provider/tester/investor/collaborator/other), possible commitments, follow-up suggestion, confidence, evidence offsets and `unknown` state. Validate strict structured JSON against typed schema. Budget and rate limits; cache by content hash/model/rule version. Prompt-injection defense: email content is untrusted data, never instructions. Store model version and reasoning summary, not private chain-of-thought. Test hallucinations, adversarial emails and malformed model output with mocked inference. Only send permitted/redacted data after explicit opt-in.

M6 — Local dashboard: `Needs review`, `Needs reply (confirmed)`, `Waiting on them`, `Follow up`, `Resolved`, `Ignored`; allow search, edits, evidence links, export, and manual confirmation. Do not auto-send anything.

M7 — Design a connector interface for future iPhone-to-macOS notification capture, but do NOT promise reliable access until tested with macOS permissions and real sample notifications.

## Acceptance criteria

- Clean install and one documented command to execute offline tests.
- No network/Meta/Gmail calls during unit tests.
- No secrets or personal data committed, including email previews from a real inbox.
- Gmail sync can be interrupted and restarted without data loss, duplicate actions or premature cursor advancement.
- An incoming notification never by itself asserts `needs_reply` without additional evidence or human confirmation.
- Rule-only mode works without Meta credentials, and Meta calls are disabled by default.
- Provide an end-to-end demo using entirely synthetic fixtures and a concise setup guide for real Gmail OAuth.

## First response / first change

Start by reviewing repo status and listing the three highest-risk engineering assumptions. Then implement M1 with red-green-refactor tests and report test output. Do not implement all milestones in a single large PR. Open a short GitHub issue/PR per milestone if tooling permits.
