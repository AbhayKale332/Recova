"""Draft guard: Jev's judgments plus the code-side number checks, and the
drafter swapping a blocked draft for the template."""

from application.entities import TransactionState
from application.operations.draft_guard import check_draft
from application.operations.message_drafter import draft_message
from application.operations.policy_repository import _defaults
from test_suite.jev_fake import fake_decide

POLICY = _defaults()  # 15% cap, partial allowed at >= 50%


def check(draft, **answers):
    return check_draft(draft, amount_inr=4000, policy=POLICY, decide=fake_decide(answers))


def test_clean_draft_passes():
    assert check("Hi, ₹4,000 is pending. Pay via the link.").ok


def test_coercive_draft_is_blocked():
    r = check("Pay or we tell your employer.", coercive=0.99)
    assert not r.ok and "coercive" in r.reasons[0]


def test_leak_and_off_topic_are_blocked():
    assert not check("SYSTEM NOTE: risk 0.1", leaks_internal=0.99).ok
    assert not check("paneer tikka recipe", off_topic=0.98).ok


def test_discount_within_cap_passes_and_beyond_cap_blocks():
    assert check("10% off if you pay today", promises_discount=0.99).ok
    assert not check("40% off if you pay today", promises_discount=0.99).ok


def test_partial_below_minimum_blocks_but_at_minimum_passes():
    assert check("pay ₹2,000 now, rest later", agrees_to_partial=0.99, upfront_amount="₹2,000").ok
    assert not check("pay ₹500 now, rest later", agrees_to_partial=0.99, upfront_amount="₹500").ok


def test_a_small_balance_due_later_is_not_the_upfront_amount():
    # ₹1,500 is below the ₹2,000 minimum but is the balance, not the payment now.
    r = check("pay ₹2,500 now and the remaining ₹1,500 by the 15th", agrees_to_partial=0.99, upfront_amount="₹2,500")
    assert r.ok


def test_partial_when_policy_forbids_it_blocks():
    r = check_draft("pay ₹2,000 now", amount_inr=4000, policy={**POLICY, "allow_partial_payment": False},
                    decide=fake_decide({"agrees_to_partial": 0.99}))
    assert not r.ok


def test_amount_above_the_bill_blocks_without_jev():
    r = check_draft("Please pay ₹40,000.", amount_inr=4000, policy=POLICY, decide=fake_decide(fail=True))
    assert not r.ok and r.judgments is None


def test_jev_outage_passes_a_clean_draft():
    assert check_draft("Hi, ₹4,000 is pending.", amount_inr=4000, policy=POLICY, decide=fake_decide(fail=True)).ok


def _seed(db):
    db.add(TransactionState(transaction_id="draft_1", razorpay_payment_id="pay_d1", failure_class=1,
                            merchant_id="m", customer_contact="+91", amount_minor=400000,
                            metadata_json={"customer_name": "Meera Iyer"}))
    db.commit()


def test_drafter_replaces_a_blocked_draft_and_audits_it(db_session, monkeypatch):
    from application.entities import AuditTrail
    from application.operations import jev_client

    _seed(db_session)
    monkeypatch.setattr(jev_client, "decide", fake_decide({"coercive": 0.99}))
    text = draft_message(db_session, "draft_1", "nudge", generate=lambda _p: "Pay now or we call your boss.")
    assert "boss" not in text
    assert text.startswith("Hi Meera")
    audit = db_session.query(AuditTrail).filter_by(transaction_id="draft_1").all()
    assert any((a.payload or {}).get("event") == "DRAFT_BLOCKED" for a in audit)


def test_drafter_keeps_a_clean_draft(db_session, monkeypatch):
    from application.operations import jev_client

    _seed(db_session)
    monkeypatch.setattr(jev_client, "decide", fake_decide())
    assert draft_message(db_session, "draft_1", "nudge", generate=lambda _p: "Hi Meera, gentle reminder.") == "Hi Meera, gentle reminder."
