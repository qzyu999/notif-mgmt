# Architecture decision log

- **2026-11-02 — Private, local-first MVP:** use SQLite and exportable schema to avoid service lock-in and protect personal messages.
- **2026-11-02 — Gmail before notifications:** supported read-only API with incremental sync; notification capture remains an experimental follow-up.
- **2026-11-02 — Rules before AI:** parse standardized notification templates deterministically. Invoke the model only when useful and explicitly permitted.
- **2026-11-02 — Human approval:** no sending emails or social replies; generated CRM follow-ups are suggestions, not side effects.
