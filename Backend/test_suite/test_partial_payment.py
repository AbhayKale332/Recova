"""Tests for partial payment link generation, merchant policy guardrails, and link deactivation."""

from datetime import datetime

from application.constants import (
    FailureClass,
    InterventionAction,
    PaymentArtifactKind,
    PaymentArtifactStatus,
)
from application.entities import Message, PaymentArtifact, TransactionState
from application.helpers import IST
from application.operations import payment_artifacts
from application.operations.agent_tools import AgentDecision, AgentTool, gate_tool
from application.operations.model_router import explain_route
from application.operations.policy_guard import PolicySandbox, ProposedAction


def test_policy_sandbox_rejects_partial_when_disabled():
    policy = {
        "allowed_actions": ["GENERATE_PAYMENT_LINK"],
        "allowed_channels": ["PAYMENT_LINK"],
        "max_discount_pct": 10,
        "max_intervention_amount_minor": 1000000,
        "allow_partial_payment": False,
        "min_partial_payment_pct": 50,
    }
    sandbox = PolicySandbox(policy)

    # Full payment is allowed
    full_action = ProposedAction(
        action=InterventionAction.GENERATE_PAYMENT_LINK,
        channel="PAYMENT_LINK",
        amount_minor=500000,
        total_amount_minor=500000,
    )
    assert sandbox.validate(full_action).approved is True

    # Partial payment is rejected
    partial_action = ProposedAction(
        action=InterventionAction.GENERATE_PAYMENT_LINK,
        channel="PAYMENT_LINK",
        amount_minor=300000,
        total_amount_minor=500000,
    )
    decision = sandbox.validate(partial_action)
    assert decision.approved is False
    assert "not permitted by merchant policy" in decision.reason


def test_policy_sandbox_enforces_min_partial_percentage():
    policy = {
        "allowed_actions": ["GENERATE_PAYMENT_LINK"],
        "allowed_channels": ["PAYMENT_LINK"],
        "max_discount_pct": 10,
        "max_intervention_amount_minor": 1000000,
        "allow_partial_payment": True,
        "min_partial_payment_pct": 50,
    }
    sandbox = PolicySandbox(policy)

    # 60% partial payment (₹3,000 / ₹5,000) -> approved
    approved_action = ProposedAction(
        action=InterventionAction.GENERATE_PAYMENT_LINK,
        channel="PAYMENT_LINK",
        amount_minor=300000,
        total_amount_minor=500000,
    )
    assert sandbox.validate(approved_action).approved is True

    # 20% partial payment (₹1,000 / ₹5,000) -> rejected
    rejected_action = ProposedAction(
        action=InterventionAction.GENERATE_PAYMENT_LINK,
        channel="PAYMENT_LINK",
        amount_minor=100000,
        total_amount_minor=500000,
    )
    decision = sandbox.validate(rejected_action)
    assert decision.approved is False
    assert "below the 50% policy minimum" in decision.reason


def test_minting_partial_link_graciously_closes_previous_active_link(db_session):
    txn = TransactionState(
        transaction_id="txn_partial_test_1",
        razorpay_payment_id="pay_test_123",
        failure_class=FailureClass.REALTIME_DEGRADATION,
        merchant_id="m1",
        customer_contact="+919999999999",
        amount_minor=500000,  # ₹5,000
    )
    db_session.add(txn)
    db_session.commit()

    # 1. Mint initial full payment link
    art1 = payment_artifacts.mint(
        db_session,
        txn,
        PaymentArtifactKind.LINK,
        amount_minor=500000,
    )
    assert art1.status == PaymentArtifactStatus.CREATED

    # Add a conversation message holding art1
    msg1 = Message(
        transaction_id=txn.transaction_id,
        seq=1,
        sender="AGENT",
        direction="OUTBOUND",
        body="Here is your link",
        meta_json={"payment_artifact": art1.as_dict()},
    )
    db_session.add(msg1)
    db_session.commit()

    # 2. Mint partial payment link for ₹3,000
    art2 = payment_artifacts.mint(
        db_session,
        txn,
        PaymentArtifactKind.LINK,
        amount_minor=300000,
        accept_partial=True,
        first_min_partial_minor=300000,
    )

    db_session.refresh(art1)
    db_session.refresh(msg1)

    # Verify previous link was closed
    assert art1.status == PaymentArtifactStatus.CLOSED
    assert art2.status == PaymentArtifactStatus.CREATED
    assert art2.amount_minor == 300000
    assert art2.accept_partial is True

    # Verify previous message meta was updated to closed
    assert msg1.meta_json["payment_artifact"]["status"] == "closed"


def test_live_session_run_agent_tool_generates_partial_payment_link_and_closes_previous(db_session):
    from application.operations.live_session import create_session
    from application.simulation.scenario import CustomCase

    case = CustomCase(
        transaction_id="txn_live_partial_test",
        customer_name="Aarav Sharma",
        failure_class=1,
        amount_inr=5000,
    )
    session = create_session(db_session, custom_case=case.model_dump())
    session.start(db_session)

    # Initial opening created an artifact for 5000
    artifacts_1 = session.list_artifacts(db_session)
    assert len(artifacts_1) == 1
    assert artifacts_1[0]["amount_minor"] == 500000
    assert artifacts_1[0]["status"] == "created"

    # Request partial payment link for 3000
    res = session.run_agent_tool(db_session, "GENERATE_PAYMENT_LINK", {"amount_inr": 3000})
    assert res["allowed"] is True
    assert res["artifact"]["amount_minor"] == 300000
    assert res["artifact"]["accept_partial"] is True

    # Verify previous artifact is closed and new artifact is created
    artifacts_2 = session.list_artifacts(db_session)
    assert len(artifacts_2) == 2
    old_art = [a for a in artifacts_2 if a["id"] == artifacts_1[0]["id"]][0]
    new_art = [a for a in artifacts_2 if a["id"] == res["artifact"]["id"]][0]
    assert old_art["status"] == "closed"
    assert new_art["status"] == "created"
