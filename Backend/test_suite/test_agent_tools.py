"""Closed agent-tool resolution and deterministic gate tests."""

import json
from datetime import date, datetime

import pytest

from application.constants import (
    ActionType,
    FailureClass,
    InterventionAction,
    InterventionChannel,
    NodeName,
    Outcome,
    StoppingRule,
    TransactionLifecycleState,
)
from application.entities import TransactionState
from application.helpers import IST, next_salary_window
from application.operations.agent_tools import AgentTool, decide_tool
from application.operations.audit_service import record_audit
from application.operations.model_router import ProviderUnavailable, RoutedResult, explain_route
from application.operations.policy_repository import update_policy


class FakeRouter:
    def __init__(self, payload=None, unavailable=False):
        self.payload = payload or {"tool": "SEND_WHATSAPP", "reason": "Contact the customer."}
        self.unavailable = unavailable
        self.calls = []

    def call(self, task, prompt, **kwargs):
        self.calls.append((task, prompt, kwargs))
        route = explain_route(task, **kwargs)
        if self.unavailable:
            raise ProviderUnavailable("offline", route)
        return RoutedResult(json.dumps(self.payload), route)


def _seed(db, transaction_id="agent_1", failure_class=FailureClass.REALTIME_DEGRADATION):
    db.add(
        TransactionState(
            transaction_id=transaction_id,
            razorpay_payment_id=f"pay_{transaction_id}",
            failure_class=failure_class,
            merchant_id="merchant_1",
            customer_contact="+919999999999",
            amount_minor=500000,
        )
    )
    db.commit()


@pytest.mark.parametrize(
    ("tool", "action", "channel", "state"),
    [
        (AgentTool.SEND_WHATSAPP, InterventionAction.SEND_WHATSAPP, InterventionChannel.WHATSAPP, None),
        (AgentTool.VOICE_CALL, InterventionAction.VOICE_CALL, InterventionChannel.VOICE, None),
        (
            AgentTool.GENERATE_PAYMENT_LINK,
            InterventionAction.GENERATE_PAYMENT_LINK,
            InterventionChannel.PAYMENT_LINK,
            None,
        ),
        (AgentTool.OFFER_FEE_WAIVER, InterventionAction.OFFER_FEE_WAIVER, InterventionChannel.WHATSAPP, None),
        (AgentTool.SCHEDULE_RETRY, InterventionAction.RETRY_CHARGE, None, TransactionLifecycleState.WAITING),
        (AgentTool.HANDOFF_TO_HUMAN, None, None, TransactionLifecycleState.ESCALATED),
        (AgentTool.STOP, None, None, TransactionLifecycleState.CANCELLED),
    ],
)
def test_every_agent_tool_resolves_to_its_documented_result(
    db_session, tool, action, channel, state
):
    _seed(db_session)
    decision = decide_tool(
        db_session,
        "agent_1",
        model_router=FakeRouter({"tool": tool.value, "reason": "Because it is appropriate."}),
        now_ist=datetime(2026, 9, 5, 11, 0, tzinfo=IST),
    )
    assert decision.tool == tool
    assert decision.action == action
    assert decision.channel == channel
    assert decision.terminal_state == state
    assert decision.allowed is True


@pytest.mark.parametrize(
    ("failure_class", "expected"),
    [
        (FailureClass.REALTIME_DEGRADATION, AgentTool.GENERATE_PAYMENT_LINK),
        (FailureClass.CHECKOUT_ABANDONMENT, AgentTool.SEND_WHATSAPP),
        (FailureClass.SUBSCRIPTION_MANDATE, AgentTool.SCHEDULE_RETRY),
        (FailureClass.B2B_RECEIVABLES, AgentTool.SEND_WHATSAPP),
    ],
)
def test_unknown_tool_uses_each_class_default(db_session, failure_class, expected):
    _seed(db_session, failure_class=failure_class)
    decision = decide_tool(
        db_session,
        "agent_1",
        model_router=FakeRouter({"tool": "NOT_A_TOOL", "reason": "bad proposal"}),
        now_ist=datetime(2026, 9, 5, 11, 0, tzinfo=IST),
    )
    assert decision.tool == expected


def test_policy_rejection_hands_off_with_exact_sandbox_reason(db_session):
    _seed(db_session)
    update_policy(db_session, {"max_discount_pct": 15})
    decision = decide_tool(
        db_session,
        "agent_1",
        model_router=FakeRouter(
            {"tool": "OFFER_FEE_WAIVER", "reason": "Give the customer a 20% waiver.", "discount_pct": 20}
        ),
        now_ist=datetime(2026, 9, 5, 11, 0, tzinfo=IST),
    )
    assert decision.tool == AgentTool.HANDOFF_TO_HUMAN
    assert decision.terminal_state == TransactionLifecycleState.ESCALATED
    assert decision.allowed is False
    assert decision.reason == "Discount 20% exceeds the 15% policy cap."
    assert decision.sandbox_reason == decision.reason


def test_quiet_hours_precede_retry_and_voice_caps(db_session, monkeypatch):
    _seed(db_session)

    def must_not_consult(*_args, **_kwargs):
        raise AssertionError("a later gate was consulted before quiet hours")

    monkeypatch.setattr("application.operations.agent_tools.retry_cap_exceeded", must_not_consult)
    monkeypatch.setattr("application.operations.agent_tools.voice_attempts_exhausted", must_not_consult)
    decision = decide_tool(
        db_session,
        "agent_1",
        voice_attempts=2,
        now_ist=datetime(2026, 9, 5, 21, 40, tzinfo=IST),
        model_router=FakeRouter({"tool": "VOICE_CALL", "reason": "Call now."}),
    )
    assert decision.allowed is False
    assert decision.stopping_rule == StoppingRule.TRAI_QUIET_HOURS
    assert decision.terminal_state == TransactionLifecycleState.WAITING


def test_schedule_retry_waits_for_next_salary_window(db_session):
    _seed(db_session, failure_class=FailureClass.SUBSCRIPTION_MANDATE)
    decision = decide_tool(
        db_session,
        "agent_1",
        model_router=FakeRouter({"tool": "SCHEDULE_RETRY", "reason": "Retry after salary credit."}),
        now_ist=datetime(2026, 9, 5, 11, 0, tzinfo=IST),
    )
    assert decision.tool == AgentTool.SCHEDULE_RETRY
    assert decision.terminal_state == TransactionLifecycleState.WAITING
    assert decision.scheduled_for == next_salary_window(date.today())


def test_stop_cancels(db_session):
    _seed(db_session)
    decision = decide_tool(
        db_session,
        "agent_1",
        model_router=FakeRouter({"tool": "STOP", "reason": "Customer opted out."}),
        now_ist=datetime(2026, 9, 5, 11, 0, tzinfo=IST),
    )
    assert decision.terminal_state == TransactionLifecycleState.CANCELLED
    assert decision.allowed is True


def _seed_whatsapp_nudges(db, count, transaction_id="agent_1"):
    for _ in range(count):
        record_audit(
            db,
            transaction_id=transaction_id,
            node_name=NodeName.EXECUTE_INTERVENTION,
            action_type=ActionType.INTERVENTION_DISPATCH,
            payload={"action": "SEND_WHATSAPP", "channel": InterventionChannel.WHATSAPP.value},
            outcome=Outcome.SUCCESS,
        )


def test_third_whatsapp_nudge_auto_escalates_to_a_voice_call(db_session):
    _seed(db_session, failure_class=FailureClass.CHECKOUT_ABANDONMENT)
    _seed_whatsapp_nudges(db_session, 3)
    decision = decide_tool(
        db_session,
        "agent_1",
        model_router=FakeRouter({"tool": "SEND_WHATSAPP", "reason": "Nudge again."}),
        now_ist=datetime(2026, 9, 5, 11, 0, tzinfo=IST),
    )
    assert decision.tool == AgentTool.VOICE_CALL
    assert decision.channel == InterventionChannel.VOICE
    assert decision.allowed is True
    assert "Auto-escalated" in decision.model_reason


def test_two_whatsapp_nudges_do_not_escalate(db_session):
    _seed(db_session, failure_class=FailureClass.CHECKOUT_ABANDONMENT)
    _seed_whatsapp_nudges(db_session, 2)
    decision = decide_tool(
        db_session,
        "agent_1",
        model_router=FakeRouter({"tool": "SEND_WHATSAPP", "reason": "Nudge again."}),
        now_ist=datetime(2026, 9, 5, 11, 0, tzinfo=IST),
    )
    assert decision.tool == AgentTool.SEND_WHATSAPP


def test_nudge_cap_does_not_override_when_voice_attempts_exhausted(db_session):
    _seed(db_session, failure_class=FailureClass.CHECKOUT_ABANDONMENT)
    _seed_whatsapp_nudges(db_session, 3)
    decision = decide_tool(
        db_session,
        "agent_1",
        voice_attempts=2,
        model_router=FakeRouter({"tool": "SEND_WHATSAPP", "reason": "Nudge again."}),
        now_ist=datetime(2026, 9, 5, 11, 0, tzinfo=IST),
    )
    assert decision.tool == AgentTool.SEND_WHATSAPP


def test_provider_unavailable_uses_class_default(db_session):
    _seed(db_session, failure_class=FailureClass.CHECKOUT_ABANDONMENT)
    decision = decide_tool(
        db_session,
        "agent_1",
        model_router=FakeRouter(unavailable=True),
        now_ist=datetime(2026, 9, 5, 11, 0, tzinfo=IST),
    )
    assert decision.tool == AgentTool.SEND_WHATSAPP
    assert decision.route_decision.task == "DECIDE"


# ---------------------------------------------------------------- Jev DECIDE

from application.operations.reply_understanding import read_reply  # noqa: E402
from test_suite.jev_fake import fake_decide  # noqa: E402

_NOON = datetime(2026, 9, 5, 11, 0, tzinfo=IST)


def _must_not_route():
    return FakeRouter({"tool": "STOP", "reason": "the LLM must not be asked"})


def test_jev_picks_the_tool_and_the_llm_is_not_called(db_session):
    _seed(db_session)
    router = _must_not_route()
    decision = decide_tool(
        db_session, "agent_1", model_router=router, now_ist=_NOON,
        jev=fake_decide({"tool": ("GENERATE_QR_CODE", 0.9)}),
    )
    assert decision.tool == AgentTool.GENERATE_QR_CODE
    assert decision.allowed is True
    assert router.calls == []
    assert decision.route_decision.provider == "openrouter"
    assert decision.route_decision.task == "DECIDE"
    assert "Jev chose GENERATE_QR_CODE" in decision.model_reason


def test_jev_low_confidence_uses_the_class_default(db_session):
    _seed(db_session, failure_class=FailureClass.SUBSCRIPTION_MANDATE)
    decision = decide_tool(
        db_session, "agent_1", model_router=_must_not_route(), now_ist=_NOON,
        jev=fake_decide({"tool": ("VOICE_CALL", 0.3)}),
    )
    assert decision.tool == AgentTool.SCHEDULE_RETRY
    assert "class default" in decision.model_reason


def test_jev_outage_falls_back_to_the_llm(db_session):
    _seed(db_session)
    router = FakeRouter({"tool": "SEND_WHATSAPP", "reason": "LLM fallback"})
    decision = decide_tool(
        db_session, "agent_1", model_router=router, now_ist=_NOON, jev=fake_decide(fail=True),
    )
    assert [c[0] for c in router.calls] == ["DECIDE"]
    assert decision.tool == AgentTool.SEND_WHATSAPP


def test_use_jev_false_never_asks_jev(db_session):
    _seed(db_session)
    calls = []
    decide_tool(
        db_session, "agent_1", model_router=FakeRouter(), now_ist=_NOON,
        jev=fake_decide(calls=calls), use_jev=False,
    )
    assert calls == []


def _partial_turn(db_session, rupees):
    text = f"abhi {rupees} de sakta hoon, 15 tarikh ko baaki"
    label = f"₹{rupees:,}"
    reading = read_reply(
        text, today=_NOON.date(),
        decide=fake_decide({"commits_to_pay": 0.95, "p2p_when": "day_of_month", "p2p_number": "15", "offer_amount": label}),
    )
    return decide_tool(
        db_session, "agent_1", model_router=_must_not_route(), now_ist=_NOON,
        customer_text=text, reading=reading, jev=fake_decide({"tool": ("OFFER_PARTIAL_PLAN", 0.9)}),
    )


def test_offer_amount_and_p2p_become_partial_amount_and_deadline(db_session):
    _seed(db_session)  # ₹5,000
    decision = _partial_turn(db_session, 3000)
    assert decision.tool == AgentTool.OFFER_PARTIAL_PLAN
    assert decision.allowed is True
    assert decision.request_amount_minor == 300000
    assert decision.deadline_days == 10


def test_offer_below_policy_minimum_is_refused_by_the_sandbox(db_session):
    _seed(db_session)  # ₹5,000; 50% minimum
    decision = _partial_turn(db_session, 2000)
    assert decision.allowed is False
    assert decision.tool == AgentTool.HANDOFF_TO_HUMAN
    assert "below the 50% policy minimum" in decision.reason


def test_policy_forbidden_tools_are_not_offered(db_session):
    _seed(db_session)
    update_policy(db_session, {"allowed_actions": ["SEND_WHATSAPP", "GENERATE_PAYMENT_LINK"]})
    calls = []
    decide_tool(
        db_session, "agent_1", model_router=_must_not_route(), now_ist=_NOON,
        jev=fake_decide({"tool": ("SEND_WHATSAPP", 0.9)}, calls=calls),
    )
    offered = set(calls[0]["questions"]["tool"]["criteria"])
    assert "VOICE_CALL" not in offered and "OFFER_FEE_WAIVER" not in offered
    assert {"SEND_WHATSAPP", "GENERATE_PAYMENT_LINK", "HANDOFF_TO_HUMAN", "STOP"} <= offered
