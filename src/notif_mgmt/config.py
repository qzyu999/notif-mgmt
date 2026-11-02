"""Environment-driven configuration. No model names, endpoints, or secrets
are hardcoded; excerpt sizing is the first consumer."""
import os

DEFAULT_EXCERPT_CHARS = 200


def excerpt_chars() -> int:
    raw = os.environ.get("NOTIF_MGMT_EXCERPT_CHARS", "")
    try:
        return max(0, int(raw)) if raw else DEFAULT_EXCERPT_CHARS
    except ValueError:
        return DEFAULT_EXCERPT_CHARS
