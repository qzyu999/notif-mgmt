# Engineering instructions — notif-mgmt

## Product invariants

1. Local-first and vendor-neutral: no Beeper, Matrix, or Meta lock-in. Connector and model interfaces must be replaceable.
2. Read-only ingestion in the MVP. No emailing, replying, connecting to social accounts, mass outreach, or browser automation.
3. Treat each notification as **evidence of an event**, not an authoritative conversation transcript or proof that no reply was sent.
4. Every ingested event has stable `(source, external_id)` identity and provenance; ingestion must be idempotent.
5. The sync cursor advances only after all associated events are committed successfully. Expired Gmail history cursors require controlled recovery, not silent data loss.
6. Do not automatically merge contacts across platforms without high-confidence evidence and a reversible decision; never match solely on display name.
7. Never commit secrets, personal messages, databases or tokens. Do not upload real message content to an LLM without explicit opt-in. Log metadata, not message bodies.
8. Provide offline fixtures and mocked external integrations for deterministic tests; tests must never call Gmail or Meta by default.

## Process

- Follow red-green-refactor TDD for each component and contract; test negative paths and crash/retry paths.
- Build vertical slices, not speculative architectures. Python 3.12, SQLite, Pydantic; FastAPI + React/TypeScript/Vite only at the A5 web milestone (functionality first, deliberate visual design later in Phase B).
- Canonical model: Person/Entity → Platform Identities → Interaction Signals → Follow-ups. Source evidence is stored separately from inferred state; identity resolution is minimal (unresolved, exact email/handle match, manual link) — no name-only matching, no merge workflows until needed. A notification alone creates at most a `review` follow-up candidate, never an asserted `needs_reply`.
- For each meaningful change: explain scope, write failing tests, implement, run checks, and document evidence.
- Maintain `docs/decisions.md` for irreversible design tradeoffs and update docs and checklists alongside code.
- Keep API/model provider configuration via environment, never hardcode model names, endpoints, or keys.

## Acceptance criteria for Gmail milestone

- Initial import respects explicit query and bounded date range.
- Incremental sync resumes from persisted `historyId`, handles pagination and add/delete changes, and deduplicates replays.
- Errors leave data and cursors consistent. Handle expired cursor (HTTP 404), 429 retry, 401/403 auth failures, and interrupted runs.
- Store sender, message/thread IDs, timestamp and minimal excerpts only as configured.
- Correctly distinguish notification email from ordinary message and avoid false `needs_reply` decisions.
- Fixture-based integration test covers first sync, resumed sync, duplicate history events, crashes, deleted/removed entries, and cursor recovery.
