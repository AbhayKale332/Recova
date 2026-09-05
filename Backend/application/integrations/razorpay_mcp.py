"""Private Razorpay MCP dispatch adapter.

Central invariant: the model must never see the MCP tool list, and no MCP tool
name may appear in a DECIDE prompt or reach ``AgentTool``. The model proposes
from the closed seven-tool ``AgentTool`` set; quiet hours, retry cap, voice cap,
and ``PolicySandbox.validate()`` run in that order; only then does this module
serve as the final payment dispatch transport.

The Python MCP SDK is intentionally imported lazily here. The connection is
process-local, just like the live-session queue in ``operations/live_session.py``.
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import json
import threading
from collections.abc import Callable, Mapping
from contextlib import AsyncExitStack
from typing import Any

import httpx

from application.settings import settings


RAZORPAY_MCP_ALLOWLIST = frozenset(
    {
        "create_payment_link",
        "create_payment_link_upi",
        "create_qr_code",
        "fetch_payment_link",
        "fetch_payment",
        "capture_payment",
    }
)

_RENDER_TOOL_BY_FAILURE_CLASS = {
    1: "create_payment_link",
    2: "create_payment_link_upi",
    3: "create_qr_code",
    4: "create_payment_link",
}
_RENDER_VARIANT_BY_FAILURE_CLASS = {
    1: "link",
    2: "upi",
    3: "qr",
    4: "link",
}

_loop_lock = threading.Lock()
_background_loop: asyncio.AbstractEventLoop | None = None
_background_thread: threading.Thread | None = None
_client_lock = threading.Lock()
_default_client: "RazorpayMCPClient" | None = None
_default_client_config: tuple[str, str, str] | None = None


def _run_background_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


def _get_background_loop() -> asyncio.AbstractEventLoop:
    global _background_loop, _background_thread
    with _loop_lock:
        if _background_loop is None:
            _background_loop = asyncio.new_event_loop()
            _background_thread = threading.Thread(
                target=_run_background_loop,
                args=(_background_loop,),
                name="razorpay-mcp-loop",
                daemon=True,
            )
            _background_thread.start()
        return _background_loop


def payment_render_variant(failure_class: int) -> str:
    """Return the deterministic link/UPI/QR rendering variant for class 1-4."""

    try:
        return _RENDER_VARIANT_BY_FAILURE_CLASS[int(failure_class)]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"unknown payment failure class: {failure_class!r}") from exc


def payment_tool_for_failure_class(failure_class: int) -> str:
    """Return the private MCP transport operation for a payment rendering variant."""

    try:
        return _RENDER_TOOL_BY_FAILURE_CLASS[int(failure_class)]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"unknown payment failure class: {failure_class!r}") from exc


def test_key_allowed(key_id: str, *, allow_live_keys: bool) -> bool:
    """Guard the remote transport against accidental live-key use."""

    return bool(key_id) and (allow_live_keys or key_id.startswith("rzp_test_"))


def mcp_dispatch_enabled() -> bool:
    """Whether settings authorize an MCP attempt for the current Razorpay keys."""

    return bool(
        settings.razorpay_mcp_enabled
        and settings.razorpay_key_id
        and settings.razorpay_key_secret
        and test_key_allowed(
            settings.razorpay_key_id,
            allow_live_keys=settings.razorpay_mcp_allow_live_keys,
        )
    )


def default_client() -> "RazorpayMCPClient":
    """Return the process-local client whose session is reused between dispatches."""

    # This MCP session is per-process, like the live-session queue in operations/live_session.py.
    global _default_client, _default_client_config
    config = (
        settings.razorpay_mcp_url,
        settings.razorpay_key_id,
        settings.razorpay_key_secret,
    )
    with _client_lock:
        if _default_client is None or _default_client_config != config:
            _default_client = RazorpayMCPClient(
                url=config[0],
                key_id=config[1],
                key_secret=config[2],
            )
            _default_client_config = config
        return _default_client


def _authorization_header(key_id: str, key_secret: str) -> str:
    """Build the official remote MCP Basic merchant-token header in memory."""

    encoded = base64.b64encode(f"{key_id}:{key_secret}".encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


def assert_allowlisted_tools(tools: Any) -> None:
    """Assert that the server advertises every private operation we may call."""

    if hasattr(tools, "tools"):
        tools = tools.tools
    names = {
        item if isinstance(item, str) else getattr(item, "name", None)
        for item in tools
    }
    names.discard(None)
    missing = RAZORPAY_MCP_ALLOWLIST - names
    assert not missing, "Razorpay MCP server is missing required allowlisted tools"


def _result_data(result: Any) -> dict[str, Any] | None:
    if getattr(result, "is_error", False):
        return None
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, Mapping):
        return dict(structured)
    for block in getattr(result, "content", ()) or ():
        text = getattr(block, "text", None)
        if not isinstance(text, str):
            continue
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return None


class RazorpayMCPClient:
    """Synchronous façade over one long-lived async MCP client session."""

    def __init__(
        self,
        *,
        url: str | None = None,
        key_id: str | None = None,
        key_secret: str | None = None,
        timeout_s: float | None = None,
        session_factory: Callable[[Any, Any], Any] | None = None,
    ) -> None:
        self.url = url or settings.razorpay_mcp_url
        self.key_id = key_id if key_id is not None else settings.razorpay_key_id
        self.key_secret = key_secret if key_secret is not None else settings.razorpay_key_secret
        self.timeout_s = max(
            0.001,
            float(timeout_s if timeout_s is not None else settings.razorpay_mcp_timeout_s),
        )
        self._session: Any = None
        self._exit_stack: AsyncExitStack | None = None
        self._session_factory = session_factory

    async def _connect_async(self) -> None:
        from mcp import ClientSession
        from mcp.client.sse import sse_client
        from mcp.client.streamable_http import streamable_http_client

        auth_header = _authorization_header(self.key_id, self.key_secret)
        headers = {"Authorization": auth_header}
        last_error: Exception | None = None

        # Streamable HTTP is the official remote transport. SSE is only a
        # runtime compatibility fallback; this adapter never starts a Node subprocess.
        for transport_name in ("streamable", "sse"):
            stack = AsyncExitStack()
            try:
                http_client = httpx.AsyncClient(
                    headers=headers,
                    follow_redirects=True,
                    timeout=self.timeout_s,
                )
                await stack.enter_async_context(http_client)
                if transport_name == "streamable":
                    transport = streamable_http_client(self.url, http_client=http_client)
                else:
                    transport = sse_client(
                        self.url,
                        headers=headers,
                        timeout=self.timeout_s,
                        sse_read_timeout=self.timeout_s,
                    )
                read_stream, write_stream = await stack.enter_async_context(transport)
                session_factory = self._session_factory or ClientSession
                session = await stack.enter_async_context(session_factory(read_stream, write_stream))
                await session.initialize()
                listed = (await session.list_tools()).tools
                assert_allowlisted_tools(listed)
                self._exit_stack = stack
                self._session = session
                return
            except Exception as exc:
                last_error = exc
                await stack.aclose()

        raise RuntimeError("Razorpay MCP connection failed") from last_error

    async def _call_async(self, name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        if self._session is None:
            await self._connect_async()
        result = await self._session.call_tool(name, arguments=arguments)
        return _result_data(result)

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Call one allowlisted tool; all transport failures return ``None``.

        The explicit allowlist refusal is the only boundary error. Once a name
        is allowed, timeout, handshake, server, and malformed-result failures
        intentionally collapse to the same ``None`` fallback signal.
        """

        if name not in RAZORPAY_MCP_ALLOWLIST:
            raise ValueError("MCP operation is not allowlisted")
        future = asyncio.run_coroutine_threadsafe(
            self._call_async(name, arguments or {}),
            _get_background_loop(),
        )
        try:
            return future.result(timeout=self.timeout_s)
        except concurrent.futures.TimeoutError:
            future.cancel()
            return None
        except Exception:
            return None

    def create_payment_link(
        self,
        *,
        amount_minor: int,
        currency: str = "INR",
        contact: str | None = None,
        description: str | None = None,
        transaction_id: str | None = None,
        merchant_id: str | None = None,
        failure_class: int = 1,
    ) -> dict[str, Any] | None:
        tool = payment_tool_for_failure_class(failure_class)
        if tool == "create_qr_code":
            arguments: dict[str, Any] = {
                "type": "upi_qr",
                "name": "Payment recovery",
                "usage": "single_use",
                "fixed_amount": True,
                "payment_amount": int(amount_minor),
                "description": description or "Payment recovery",
            }
        else:
            arguments = {
                "amount": int(amount_minor),
                "currency": currency,
                "description": description or "Payment recovery",
                "customer_contact": contact,
                "notify_sms": False,
                "notify_email": False,
                "reminder_enable": False,
            }
        notes = {
            key: value
            for key, value in (("transaction_id", transaction_id), ("merchant_id", merchant_id))
            if value is not None
        }
        if notes:
            arguments["notes"] = notes
        return self.call_tool(tool, arguments)

    def fetch_payment_link(self, payment_link_id: str) -> dict[str, Any] | None:
        return self.call_tool("fetch_payment_link", {"payment_link_id": payment_link_id})

    def fetch_payment(self, payment_id: str) -> dict[str, Any] | None:
        return self.call_tool("fetch_payment", {"payment_id": payment_id})

    def capture_payment(self, payment_id: str, amount_minor: int, currency: str = "INR") -> dict[str, Any] | None:
        return self.call_tool(
            "capture_payment",
            {"payment_id": payment_id, "amount": int(amount_minor), "currency": currency},
        )
