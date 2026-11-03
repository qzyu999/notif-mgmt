"""A3 parser registry: verified-origin parsing measured on a synthetic corpus.

Key invariants under test:
- Platform origin is proven by sender-domain evidence, never by wording alone.
- Actor candidates and handle identities are extracted only from verified
  platform notifications; nothing is fabricated from unverified mail.
- Automated and unclassified mail yields signals without review follow-ups.
- A parser version bump replayed over old events cannot duplicate signals
  or follow-ups.
"""
import json
from collections import defaultdict
from pathlib import Path

import pytest

from notif_mgmt import pipeline
from notif_mgmt.models import InboundEvent
from notif_mgmt.parsing import PARSER_REGISTRY, parse_notification
from notif_mgmt.pipeline import process_event
from notif_mgmt.storage import connect, list_followups, list_signals

CORPUS = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "parser-corpus.json")
    .read_text(encoding="utf-8")
)


def _parse(case):
    return parse_notification(InboundEvent(**case["event"]))


@pytest.mark.parametrize("case", CORPUS, ids=[c["id"] for c in CORPUS])
def test_corpus_case(case):
    parsed = _parse(case)
    expected = case["expected"]
    assert parsed.platform == expected["platform"]
    assert parsed.kind == expected["kind"]
    assert parsed.actor_candidate == expected["actor"]
    identity = parsed.identity.value_normalized if parsed.identity else None
    assert identity == expected["identity"]


def _prf(cases, key):
    """Per-label precision/recall for `key` over (expected, predicted) pairs."""
    tp, fp, fn = defaultdict(int), defaultdict(int), defaultdict(int)
    for expected, predicted in cases:
        for label in {expected, predicted}:
            if expected == label and predicted == label:
                tp[label] += 1
            elif predicted == label:
                fp[label] += 1
            elif expected == label:
                fn[label] += 1
    report = {}
    for label in sorted({e for e, _ in cases} | {p for _, p in cases}):
        precision = tp[label] / (tp[label] + fp[label]) if tp[label] + fp[label] else 1.0
        recall = tp[label] / (tp[label] + fn[label]) if tp[label] + fn[label] else 1.0
        report[label] = (precision, recall)
    return report


def test_corpus_metrics():
    platform_cases, actor_cases, fabricated_identities = [], [], 0
    dm_tp = dm_fp = 0
    for case in CORPUS:
        parsed = _parse(case)
        expected = case["expected"]
        platform_cases.append((expected["platform"], parsed.platform))
        if parsed.identity is not None and expected["identity"] is None:
            fabricated_identities += 1
        if parsed.actor_candidate is not None:
            actor_cases.append((expected["actor"], parsed.actor_candidate))
        if parsed.kind == "direct_message_notification":
            dm_tp += int(expected["kind"] == "direct_message_notification")
            dm_fp += int(expected["kind"] != "direct_message_notification")
    # Nothing may be invented from unverified or ambiguous mail.
    assert fabricated_identities == 0
    # Every actor candidate we emit must be exactly right.
    assert all(e == p for e, p in actor_cases)
    # DM classification must be perfectly precise on the corpus.
    assert dm_fp == 0 and dm_tp > 0
    for platform, (precision, recall) in _prf(platform_cases, "platform").items():
        assert precision == 1.0, f"{platform} platform precision {precision}"
        assert recall == 1.0, f"{platform} platform recall {recall}"


def test_registry_covers_platforms_and_versions_are_recorded():
    for platform in ("linkedin", "x", "reddit", "instagram", "xiaohongshu"):
        assert f"{platform}-notifications" in PARSER_REGISTRY
    assert "generic-email" in PARSER_REGISTRY
    for case in CORPUS:
        parsed = _parse(case)
        assert PARSER_REGISTRY[parsed.parser_name] == parsed.parser_version


def test_platform_wording_alone_is_not_origin_evidence():
    event = InboundEvent(
        source="gmail", external_id="phish-1",
        sender="LinkedIn Security <alerts@linkedin-secure.example.invalid>",
        subject="Alex sent you a message on LinkedIn",
        preview="Click to verify your account now.",
        received_at="2026-11-02T18:00:00Z")
    parsed = parse_notification(event)
    assert parsed.platform != "linkedin"
    assert parsed.actor_candidate is None
    assert parsed.identity is None


def test_automated_and_unclassified_signals_create_no_followups(tmp_path):
    db = connect(tmp_path / "app.db")
    by_id = {case["id"]: case for case in CORPUS}
    process_event(db, InboundEvent(**by_id["li-dm-named"]["event"]))
    process_event(db, InboundEvent(**by_id["auto-github"]["event"]))
    process_event(db, InboundEvent(**by_id["misleading-phish-linkedin"]["event"]))
    kinds = {signal.kind for signal in list_signals(db)}
    assert kinds == {"direct_message_notification", "automated_notification",
                     "unclassified_email"}
    followups = list_followups(db)
    assert len(followups) == 1  # only the verified DM asks for review
    assert followups[0].kind == "review" and followups[0].status == "open"


def test_parser_upgrade_replay_cannot_duplicate_signals_or_followups(tmp_path,
                                                                     monkeypatch):
    db = connect(tmp_path / "app.db")
    case = next(c for c in CORPUS if c["id"] == "li-dm-named")
    assert process_event(db, InboundEvent(**case["event"])) is not None
    original = pipeline.parse_notification

    def bumped(event):
        return original(event).model_copy(
            update={"parser_name": "linkedin-notifications", "parser_version": "99"})

    monkeypatch.setattr(pipeline, "parse_notification", bumped)
    assert process_event(db, InboundEvent(**case["event"])) is None
    assert len(list_signals(db)) == 1
    assert len(list_followups(db)) == 1
    # The historical signal keeps its original parser stamp.
    assert list_signals(db)[0].parser_version != "99"
