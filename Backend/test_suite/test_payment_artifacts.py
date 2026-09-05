"""Tests for the partial-plan ceiling beat and the direct agent-tool endpoint."""

from datetime import datetime

import pytest

from application.constants import (
    FailureClass,
    InterventionAction,
    PaymentArtifactKind,
    PaymentArtifactStatus,
    TransactionLifecycleState,
)
from application.entities import TransactionState
from application.helpers import IST
from application.operations import agent_tools, payment_artifacts
from application.operations.agent_tools import AgentTool, gate_tool
from application.operations.live_session import create_session, get_session
from application.operations.model_router import explain_route


def _seed_big_case(db, transaction_id="big_1"):
    db.add(
        TransactionState(
            transaction_id=transaction_id,
            razorpay_payment_id=f"pay_{transaction_id}",
            failure_class=FailureClass.REALTIME_DEGRADATION,
            merchant_id="merchant_1",
            customer_contact="+919999999999",
            amount_minor=4_800_000,  # ₹48,000
        )
    )
    db.commit()


def test_full_link_over_ceiling_is_refused_but_partial_plan_passes(db_session):
    _seed_big_case(db_session)
    txn = db_session.query(TransactionState).filter_by(transaction_id="big_1").one()
    route = explain_route("DECIDE", amount_inr=48000)

    full = gate_tool(
        db_session,
        txn,
        AgentTool.GENERATE_PAYMENT_LINK,
        route_decision=route,
        now_ist=datetime(2026, 9, 5, 11, 0, tzinfo=IST),
    )
    assert full.allowed is False
    assert "₹48,000" in full.reason and "₹10,000" in full.reason

    db_session.refresh(txn)
    partial = gate_tool(
        db_session,
        txn,
        AgentTool.OFFER_PARTIAL_PLAN,
        route_decision=route,
        request_amount_minor=950000,  # ₹9,500
        deadline_days=14,
        now_ist=datetime(2026, 9, 5, 11, 0, tzinfo=IST),
    )
    assert partial.allowed is True
    assert partial.request_amount_minor == 950000

    artifact = payment_artifacts.mint(
        db_session,
        txn,
        PaymentArtifactKind.LINK,
        amount_minor=950000,
        accept_partial=True,
        first_min_partial_minor=950000,
        deadline=datetime(2026, 9, 19, 11, 0, tzinfo=IST),
    )
    assert artifact.simulated is True
    db_session.refresh(txn)
    assert txn.metadata_json["balance_due_minor"] == 3_850_000


def test_agent_tool_endpoint_refuses_over_ceiling_and_mints_nothing(client, db_session, monkeypatch):
    from application.operations import agent_tools as agent_tools_module

    monkeypatch.setattr(
        agent_tools_module,
        "_now_ist",
        lambda: datetime(2026, 9, 5, 11, 0, tzinfo=IST),
    )
    created = client.post(
        "/api/v1/live/sessions",
        json={
            "custom_case": {
                "customer_name": "Rahul",
                "amount_inr": 48000,
                "failure_class": 1,
            }
        },
    ).json()
    session_id = created["session_id"]
    session = get_session(session_id)
    session.start(db_session)

    resp = client.post(
        f"/api/v1/live/sessions/{session_id}/agent/tool",
        json={"tool": "GENERATE_PAYMENT_LINK", "args": {}},
    )
    body = resp.json()
    assert body["allowed"] is False
    assert "policy ceiling" in body["sandbox_reason"]
    assert body["artifact"] is None

    from application.entities import PaymentArtifact

    assert db_session.query(PaymentArtifact).filter_by(transaction_id=session.transaction_id).count() == 0


def test_qr_mint_without_mcp_falls_back_to_simulated_with_no_image(db_session, monkeypatch):
    from application.integrations import razorpay_mcp

    monkeypatch.setattr(razorpay_mcp.settings, "razorpay_mcp_enabled", False)
    _seed_big_case(db_session, "qr_1")
    txn = db_session.query(TransactionState).filter_by(transaction_id="qr_1").one()

    artifact = payment_artifacts.mint(db_session, txn, PaymentArtifactKind.QR, amount_minor=10000)

    assert artifact.simulated is True
    assert artifact.detail == "simulated"
    assert artifact.provider_id is None
    assert artifact.url is None
    assert artifact.image_url is None
    assert artifact.status == PaymentArtifactStatus.CREATED


def test_simulate_paid_marks_artifact_paid_and_recovers_case(db_session, monkeypatch):
    from application.integrations import razorpay_mcp

    monkeypatch.setattr(razorpay_mcp.settings, "razorpay_mcp_enabled", False)
    _seed_big_case(db_session, "qr_2")
    txn = db_session.query(TransactionState).filter_by(transaction_id="qr_2").one()
    artifact = payment_artifacts.mint(db_session, txn, PaymentArtifactKind.QR, amount_minor=10000)

    updated = payment_artifacts.simulate_paid(db_session, artifact)

    assert updated.status == PaymentArtifactStatus.PAID
    assert updated.amount_paid_minor == 10000
    db_session.refresh(txn)
    assert txn.current_state == TransactionLifecycleState.RECOVERED


def test_simulate_paid_refuses_an_already_paid_artifact(db_session, monkeypatch):
    from application.integrations import razorpay_mcp

    monkeypatch.setattr(razorpay_mcp.settings, "razorpay_mcp_enabled", False)
    _seed_big_case(db_session, "qr_3")
    txn = db_session.query(TransactionState).filter_by(transaction_id="qr_3").one()
    artifact = payment_artifacts.mint(db_session, txn, PaymentArtifactKind.QR, amount_minor=10000)
    payment_artifacts.simulate_paid(db_session, artifact)

    with pytest.raises(ValueError):
        payment_artifacts.simulate_paid(db_session, artifact)


def test_simulate_pay_endpoint_announces_payment_in_the_thread(client, db_session, monkeypatch):
    from application.integrations import razorpay_mcp

    monkeypatch.setattr(razorpay_mcp.settings, "razorpay_mcp_enabled", False)
    created = client.post(
        "/api/v1/live/sessions",
        json={
            "custom_case": {
                "customer_name": "Asha",
                "amount_inr": 100,
                "failure_class": 3,
            }
        },
    ).json()
    session_id = created["session_id"]
    session = get_session(session_id)
    session.start(db_session)

    resp = client.post(
        f"/api/v1/live/sessions/{session_id}/agent/tool",
        json={"tool": "GENERATE_QR_CODE", "args": {}},
    )
    artifact_id = resp.json()["artifact"]["id"]

    pay_resp = client.post(f"/api/v1/live/sessions/{session_id}/artifacts/{artifact_id}/simulate-pay")
    assert pay_resp.status_code == 200
    body = pay_resp.json()
    assert body["status"] == "paid"

    from application.entities import Message

    messages = (
        db_session.query(Message)
        .filter_by(transaction_id=session.transaction_id)
        .order_by(Message.seq)
        .all()
    )
    assert any(m.meta_json and m.meta_json.get("payment_confirmed") for m in messages)

    # A second attempt against the now-paid artifact is a conflict, not a
    # silent no-op — the demo button should not be able to double-announce.
    again = client.post(f"/api/v1/live/sessions/{session_id}/artifacts/{artifact_id}/simulate-pay")
    assert again.status_code == 409


def test_simulate_pay_endpoint_404s_for_unknown_artifact(client, db_session):
    created = client.post(
        "/api/v1/live/sessions",
        json={"custom_case": {"customer_name": "Vikram", "amount_inr": 100, "failure_class": 1}},
    ).json()
    session_id = created["session_id"]
    get_session(session_id).start(db_session)

    resp = client.post(f"/api/v1/live/sessions/{session_id}/artifacts/999999/simulate-pay")
    assert resp.status_code == 404


def test_agent_tool_endpoint_rejects_unknown_function_name(client, db_session):
    created = client.post(
        "/api/v1/live/sessions",
        json={
            "custom_case": {
                "customer_name": "Priya",
                "amount_inr": 4000,
                "failure_class": 1,
            }
        },
    ).json()
    session_id = created["session_id"]
    get_session(session_id).start(db_session)

    from application.entities import PaymentArtifact

    before = db_session.query(PaymentArtifact).count()
    resp = client.post(
        f"/api/v1/live/sessions/{session_id}/agent/tool",
        json={"tool": "DROP_TABLE_PAYMENTS", "args": {}},
    )
    assert resp.status_code == 422
    assert db_session.query(PaymentArtifact).count() == before
