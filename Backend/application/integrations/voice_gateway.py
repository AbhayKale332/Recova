"""Vapi voice adapter with allowlist guard and safe simulated fallback."""

from __future__ import annotations

import uuid
from typing import Any
import httpx

from application.integrations.adapter_base import DispatchResult
from application.settings import settings

_CHANNEL = "VOICE"


class VoiceAdapter:
    def __init__(
        self,
        live_mode: bool,
        api_key: str | None = None,
        allowed_numbers: list[str] | str | None = None,
        client: Any | None = None,
    ):
        self._live = live_mode
        self._api_key = settings.vapi_api_key if api_key is None else api_key
        if allowed_numbers is None:
            self._allowed_numbers = set(settings.vapi_allowed_numbers_list)
        elif isinstance(allowed_numbers, str):
            self._allowed_numbers = {n.strip() for n in allowed_numbers.split(",") if n.strip()}
        else:
            self._allowed_numbers = set(allowed_numbers)
        self._client = client

    def call(self, to: str, script: str) -> DispatchResult:
        if not self._live or not self._api_key:
            detail = None if self._api_key else "vapi_not_configured"
            return DispatchResult(
                _CHANNEL,
                delivered=True,
                simulated=True,
                reference=f"sim_{uuid.uuid4().hex[:12]}",
                detail=detail,
            )

        contact = (to or "").strip()
        if contact not in self._allowed_numbers:
            return DispatchResult(
                _CHANNEL,
                delivered=True,
                simulated=True,
                reference=f"sim_{uuid.uuid4().hex[:12]}",
                detail="number_not_allowlisted",
            )

        url = "https://api.vapi.ai/call"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "customer": {"number": contact},
        }
        if settings.vapi_phone_number_id:
            payload["phoneNumberId"] = settings.vapi_phone_number_id
        if settings.vapi_assistant_id:
            payload["assistantId"] = settings.vapi_assistant_id
        else:
            payload["assistant"] = {
                "firstMessage": script,
            }

        try:
            if self._client is not None:
                resp = self._client.post(url, json=payload, headers=headers)
            else:
                resp = httpx.post(url, json=payload, headers=headers, timeout=10.0)

            status_code = getattr(resp, "status_code", 0)
            if status_code in (200, 201):
                data = resp.json() if callable(getattr(resp, "json", None)) else {}
                call_ref = data.get("id") or f"vapi_{uuid.uuid4().hex[:12]}"
                return DispatchResult(
                    _CHANNEL,
                    delivered=True,
                    simulated=False,
                    reference=call_ref,
                )
            return DispatchResult(
                _CHANNEL,
                delivered=False,
                simulated=False,
                detail=f"vapi_http_{status_code}",
            )
        except Exception as exc:
            return DispatchResult(
                _CHANNEL,
                delivered=False,
                simulated=False,
                detail=str(exc),
            )
