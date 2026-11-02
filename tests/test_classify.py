from notif_mgmt.classify import classify
from notif_mgmt.models import InboundEvent


def event(**kwargs):
    data = dict(source="gmail", external_id="abc", sender="notifications@linkedin.com",
                subject="Alex sent you a message", preview="Hello",
                received_at="2026-11-02T00:00:00Z", platform="linkedin")
    data.update(kwargs)
    return InboundEvent(**data)


def test_detects_possible_social_message_but_does_not_assert_unreplied():
    result = classify(event())
    assert result.category == "social_message_notification"
    assert result.state == "needs_review"
    assert "cannot establish reply status" in result.reason


def test_unknown_email_conservatively_needs_review():
    result = classify(event(sender="human@example.invalid", subject="Hello", platform=None))
    assert result.category == "other_email"
    assert result.state == "needs_review"


def test_social_activity_is_not_automatically_a_message():
    result = classify(event(subject="Your post got likes", preview="Nice post"))
    assert result.category == "social_other_notification"
