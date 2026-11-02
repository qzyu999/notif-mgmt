# Gmail configuration — when M2 is implemented

1. In a Google Cloud project under your control, enable the Gmail API.
2. Configure a consent screen for your own test account, and create an installed-desktop OAuth client. Use the least privileged read-only scope needed for the feature.
3. Download credentials locally as `credentials.json`, ignored by Git. Do not paste OAuth client secrets, access tokens, or refresh tokens into an LLM chat.
4. Begin with a 30-day targeted query, or only a chosen Gmail label, to avoid unintentionally ingesting entire personal history.
5. Confirm that the `gmail.readonly` scope is sufficient for the intended endpoints, and understand Google's sensitive/restricted scope verification rules before distributing publicly.
6. Validate offline fixtures first, then run an explicit one-shot sync. Only after verification enable 5-minute scheduled polling.

This starter scaffold intentionally does not handle real Google credentials yet. See: https://developers.google.com/workspace/gmail/api/guides/sync and https://developers.google.com/workspace/gmail/api/auth/scopes
