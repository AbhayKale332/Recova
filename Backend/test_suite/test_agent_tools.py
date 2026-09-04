"""Closed agent-tool resolution and deterministic gate tests."""

import json
from datetime import date, datetime

import pytest

from application.constants import (
    FailureClass,
    InterventionAction,
    InterventionChannel,
    StoppingRule,
    TransactionLifecycleState,
)
from application.entities import TransactionState
from application.helpers import IST, next_salary_window
from application.operations.agent_tools import AgentTool, decide_tool
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
