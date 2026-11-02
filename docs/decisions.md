# Architecture decision log

- **2026-11-02 — Private, local-first MVP:** use SQLite and exportable schema to avoid service lock-in and protect personal messages.
- **2026-11-02 — Gmail before notifications:** supported read-only API with incremental sync; notification capture remains an experimental follow-up.
- **2026-11-02 — Rules before AI:** parse standardized notification templates deterministically. Invoke the model only when useful and explicitly permitted.
- **2026-11-02 — Human approval:** no sending emails or social replies; generated CRM follow-ups are suggestions, not side effects.
- **2026-11-02 — Person-centric model (M0):** canonical chain is Person/Entity → Platform Identities → Interaction Signals → Follow-ups. Source evidence (`inbound_events`) is stored separately from inferred state; the previous event-level category/state columns are legacy, not the product model.
- **2026-11-02 — Minimal identity resolution (A1):** unresolved identities, exact email/handle matching, and manual linking only. Display names are actor candidates on signals, never identities. Suggested matches and reversible merge workflows are deferred until a real need appears.
- **2026-11-02 — Review-first follow-ups:** kind (`review|reply|waiting|follow_up`) is separate from status (`open|snoozed|done|dismissed`). A notification alone creates at most a `review` candidate.
- **2026-11-02 — Python 3.12 + Pydantic:** primary runtime is Python 3.12 (CI no longer tests 3.11); Pydantic models define the canonical domain. FastAPI arrives in A5, React/TypeScript/Vite in A5, deliberate visual design in Phase B.
- **2026-11-02 — Versioned SQLite migrations:** `PRAGMA user_version` (now v2); migrations preserve data — v1 `followups` becomes `followups_v1`, v1 cursors are copied into account-scoped `sync_state`.
- **2026-11-02 — A1 verified:** 17 tests passed, ruff clean, fixture demo idempotent on replay (3 signals + 3 review candidates, then 0 new). Committed as the M0+A1 slice.
- **2026-11-02 — A2 Gmail decisions:** macOS Keychain is the preferred OAuth token store, with a documented `0600` file fallback; Gmail source events become account-scoped via migration v3; expired `historyId` cursors get bounded recovery with explicitly recorded sync gaps (`sync_gaps`); stored excerpts capped at 200 characters by default (configurable); read-only scope only; fake transport and deterministic tests before any real account is connected.
