"""No-network tests for the private Razorpay MCP dispatch transport."""

import asyncio
import base64
from types import SimpleNamespace

import pytest

from application.constants import FailureClass
from application.entities import TransactionState
from application.integrations import razorpay_mcp
from application.integrations import payment_actions
from application.integrations.payment_actions import RazorpayActionsAdapter
from application.operations import agent_tools, payment_link_service
from application.operations.live_session import get_session


def _enable_test_mcp(monkeypatch):
    monkeypatch.setattr(razorpay_mcp.settings, "razorpay_mcp_enabled", True)
    monkeypatch.setattr(razorpay_mcp.settings, "razorpay_key_id", "rzp_test_example")
    monkeypatch.setattr(razorpay_mcp.settings, "razorpay_key_secret", "secret")
    monkeypatch.setattr(razorpay_mcp.settings, "razorpay_mcp_allow_live_keys", False)


@pytest.mark.parametrize("name", ["delete_everything", "create_refund", "unknown"])
def test_non_allowlisted_mcp_tool_is_refused(name):
    client = razorpay_mcp.RazorpayMCPClient(timeout_s=0.01)
    with pytest.raises(ValueError):
        client.call_tool(name, {})


def test_connect_time_tool_assertion_requires_the_complete_allowlist():
    advertised = [SimpleNamespace(name=name) for name in razorpay_mcp.RAZORPAY_MCP_ALLOWLIST]
    razorpay_mcp.assert_allowlisted_tools(advertised)

    missing = advertised[:-1]
    with pytest.raises(AssertionError):
        razorpay_mcp.assert_allowlisted_tools(missing)


def test_mcp_call_timeout_collapses_to_the_same_failure_signal():
    client = razorpay_mcp.RazorpayMCPClient(timeout_s=0.01)

    async def slow_call(_name, _arguments):
        await asyncio.sleep(1)

    client._call_async = slow_call
    assert client.call_tool("create_payment_link", {}) is None


def test_official_basic_auth_header_is_derived_in_memory():
    expected = base64.b64encode(b"rzp_test_example:secret").decode("ascii")
    assert razorpay_mcp._authorization_header("rzp_test_example", "secret") == f"Basic {expected}"


def test_live_key_guard_requires_explicit_override(monkeypatch):
    _enable_test_mcp(monkeypatch)
    monkeypatch.setattr(razorpay_mcp.settings, "razorpay_key_id", "rzp_live_example")
    assert razorpay_mcp.mcp_dispatch_enabled() is False

    monkeypatch.setattr(razorpay_mcp.settings, "razorpay_mcp_allow_live_keys", True)
    assert razorpay_mcp.mcp_dispatch_enabled() is True


@pytest.mark.parametrize(
    ("failure_class", "variant", "tool"),
    [
        (FailureClass.REALTIME_DEGRADATION, "link", "create_payment_link"),
        (FailureClass.CHECKOUT_ABANDONMENT, "upi", "create_payment_link_upi"),
        (FailureClass.SUBSCRIPTION_MANDATE, "qr", "create_qr_code"),
        (FailureClass.B2B_RECEIVABLES, "link", "create_payment_link"),
    ],
)
def test_failure_class_selects_deterministic_rendering_variant(failure_class, variant, tool):
    assert razorpay_mcp.payment_render_variant(failure_class) == variant
    assert razorpay_mcp.payment_tool_for_failure_class(failure_class) == tool


class _FakeMCP:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def create_payment_link(self, **_kwargs):
        self.calls += 1
        return self.response


class _FakePaymentLink:
    def __init__(self, response=None, error=None):
        self.response = response or {"id": "plink_SDK"}
        self.error = error
        self.calls = 0

    def create(self, _payload):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response


class _FakeSDK:
    def __init__(self, payment_link):
        self.payment_link = payment_link


@pytest.mark.parametrize(
    ("mcp_response", "sdk_response", "expected_detail", "simulated"),
    [
        ({"id": "plink_MCP"}, {"id": "plink_SDK"}, "mcp", False),
        (None, {"id": "plink_SDK"}, "sdk", False),
        (None, None, "simulated", True),
    ],
)
def test_mcp_sdk_sim_fallback_chain_and_detail(monkeypatch, mcp_response, sdk_response, expected_detail, simulated):
    _enable_test_mcp(monkeypatch)
    mcp = _FakeMCP(mcp_response)
    sdk_link = _FakePaymentLink(response=sdk_response, error=RuntimeError("offline")) if sdk_response is None else _FakePaymentLink(sdk_response)
    result = RazorpayActionsAdapter(
        live_mode=True,
        client=_FakeSDK(sdk_link),
        mcp_client=mcp,
    ).create_payment_link(150000, "+919999999999", failure_class=1)

    assert result.detail == expected_detail
    assert result.simulated is simulated
    assert mcp.calls == 1
    assert sdk_link.calls == (0 if mcp_response else 1)


def test_disabled_mcp_keeps_existing_simulated_dispatch(monkeypatch):
    monkeypatch.setattr(razorpay_mcp.settings, "razorpay_mcp_enabled", False)
    mcp = _FakeMCP({"id": "must_not_be_used"})
    result = RazorpayActionsAdapter(live_mode=False, mcp_client=mcp).create_payment_link(100, "+91")
    assert result.detail == "simulated"
    assert result.simulated is True
    assert mcp.calls == 0


def test_live_payment_decision_exposes_the_final_dispatch_detail(client, monkeypatch):
    _enable_test_mcp(monkeypatch)
    mcp = _FakeMCP({"id": "plink_MCP"})
    monkeypatch.setattr(payment_actions, "default_client", lambda: mcp)
    created = client.post(
        "/api/v1/live/sessions",
        json={"custom_case": {"customer_name": "Asha Rao", "amount_inr": 4000, "failure_class": 1}},
    ).json()

    client.post(
        f"/api/v1/live/sessions/{created['session_id']}/reply",
        json={"text": "band karo"},
    )
    session = get_session(created["session_id"])
    events = []
    while not session.queue.empty():
        item = session.queue.get_nowait()
        if item is not None:
            events.append(item)
    dispatch = next(data for event, data in events if event == "dispatch")
    assert dispatch["detail"] == "mcp"
    assert dispatch["reference"] == "plink_MCP"


def test_payment_link_service_uses_the_same_precedence_and_detail(db_session, monkeypatch):
    _enable_test_mcp(monkeypatch)
    db_session.add(
        TransactionState(
            transaction_id="mcp_service",
            razorpay_payment_id="pay_mcp_service",
            failure_class=FailureClass.REALTIME_DEGRADATION,
            merchant_id="merchant",
            customer_contact="+919900000000",
            amount_minor=49900,
        )
    )
    db_session.commit()

    mcp = _FakeMCP({"id": "plink_MCP", "short_url": "https://rzp.io/i/mcp"})
    monkeypatch.setattr(payment_link_service, "default_client", lambda: mcp)
    first = payment_link_service.create_payment_link(db_session, "mcp_service")
    assert first["detail"] == "mcp"
    assert first["simulated"] is False

    monkeypatch.setattr(payment_link_service, "default_client", lambda: _FakeMCP(None))
    monkeypatch.setattr(
        payment_link_service,
        "_build_client",
        lambda: _FakeSDK(_FakePaymentLink({"id": "plink_SDK", "short_url": "https://rzp.io/i/sdk"})),
    )
    second = payment_link_service.create_payment_link(db_session, "mcp_service")
    assert second["detail"] == "sdk"


def test_decide_prompt_never_contains_private_mcp_tool_names():
    txn = SimpleNamespace(amount_minor=10000, retry_count=0, max_retries=3)
    prompt = agent_tools._decide_prompt(
        txn,
        FailureClass.REALTIME_DEGRADATION,
        policy={"max_discount_pct": 20},
        voice_attempts=0,
    )
    assert not any(name in prompt for name in razorpay_mcp.RAZORPAY_MCP_ALLOWLIST)
