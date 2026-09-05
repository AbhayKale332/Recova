"""Builds transient Vapi assistant configurations personalized with case facts and guardrails."""

from __future__ import annotations

from typing import Any
from sqlalchemy.orm import Session

from application.entities import TransactionState
from application.operations.conversation_service import build_call, persona_for
from application.operations.model_router import _model_for
from application.operations import policy_repository
from application.operations.speech_format import speakable
from application.settings import settings


def build_assistant(
    txn: TransactionState,
    locale: str = "en",
    bounds: dict[str, Any] | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """Build a transient Vapi assistant config fresh per call.

    Incorporates the case's customer facts, failure class script opening, and
    live guardrail state (discount cap, voice attempts remaining).
    """
    meta = txn.metadata_json or {}
    customer_name = meta.get("customer_name") or "there"
    amount_inr = float(txn.amount_minor) / 100
    failure_class = int(txn.failure_class)

    # First message from the scripted call for this failure class
    persona = persona_for(txn.id or 0)
    beat = build_call(
        failure_class=failure_class,
        name=customer_name,
        amount_inr=amount_inr,
        persona=persona,
    )
    first_message = speakable(
        beat.turns[0].text if beat.turns else f"Namaste {customer_name}, support team se call hai."
    )

    # Model routing: full tier for the configured provider
    provider = (settings.llm_provider or "openai").strip().lower()
    vapi_provider = "google" if provider == "gemini" else "openai"
    model_name = _model_for(provider, "full") or ("gemini-3-pro" if provider == "gemini" else "gpt-5.4")

    # Guardrails from bounds and policy
    max_discount_pct = 0
    allow_partial = True
    min_partial_pct = 50
    if db is not None:
        try:
            policy = policy_repository.get_policy(db)
            max_discount_pct = int(policy.get("max_discount_pct", 0))
            allow_partial = bool(policy.get("allow_partial_payment", True))
            min_partial_pct = int(policy.get("min_partial_payment_pct", 50))
        except Exception:
            max_discount_pct = 0
            allow_partial = True
            min_partial_pct = 50

    voice_used = 0
    voice_cap = 2
    if bounds and isinstance(bounds.get("voice"), dict):
        voice_used = int(bounds["voice"].get("used", 0))
        voice_cap = int(bounds["voice"].get("cap", 2))

    voice_remaining = max(0, voice_cap - voice_used)
    if voice_remaining == 1:
        voice_status = "one voice attempt remains"
    else:
        voice_status = f"{voice_remaining} voice attempts remain"

    guardrail_note = f"you may not offer more than {max_discount_pct}%; {voice_status}"
    min_partial_amount = amount_inr * (min_partial_pct / 100)
    if allow_partial:
        partial_info = f"Partial payments: ALLOWED (minimum {min_partial_pct}% of total amount, which is ₹{min_partial_amount:,.2f})."
        partial_rule = (
            f"- Check merchant policy before discussing any partial payment: partial payments are permitted but MUST be at least "
            f"{min_partial_pct}% (₹{min_partial_amount:,.2f}). If customer asks to pay less, politely refuse and ask for at least {min_partial_pct}%. "
            f"Only if they offer at least {min_partial_pct}% may you agree to generate a partial payment link."
        )
    else:
        partial_info = "Partial payments: NOT ALLOWED by merchant policy."
        partial_rule = (
            "- Check merchant policy before discussing any partial payment: partial payments are NOT permitted by policy. "
            "If customer asks to pay partially, politely refuse and insist on full payment."
        )

    lang_instruction = "Hindi / Hinglish" if locale == "hi" else "English"
    system_prompt = speakable(
        f"You are Recova's AI voice recovery assistant calling {customer_name}.\n\n"
        f"Case Facts:\n"
        f"- Customer: {customer_name}\n"
        f"- Amount: ₹{amount_inr:,.2f}\n"
        f"- Payment Failure Class: {failure_class}\n"
        f"- Primary Language: {lang_instruction}\n\n"
        f"Live Guardrail State:\n"
        f"- {guardrail_note}\n"
        f"- {partial_info}\n"
        f"- You may NOT offer a discount higher than {max_discount_pct}%.\n"
        f"{partial_rule}\n"
        f"- Respect customer disputes or opt-outs ('stop', 'band karo') immediately by acknowledging and ending gracefully.\n\n"
        f"Speech: this is a live phone call, not text. Always say any amount aloud in words "
        f"(for example 'five thousand rupees'), never as digits or a currency symbol - a listener cannot "
        f"hear a currency symbol or a comma. Speak every amount the same way the Amount fact above is written.\n\n"
        f"Tone: Professional, calm, empathetic, and reassuring."
    )

    # Vapi rejects assistant.name over 40 characters outright, and a live
    # transaction id ("sim_" + an 8-char run-id slice + "_custom_0000") can
    # push a longer prefix past that - truncate rather than fail the call.
    # This name is a transient, per-call label only, never looked up again,
    # so truncation collisions carry no correctness risk.
    name = f"recova-{txn.transaction_id}"[:40]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "generate_payment_link",
                "description": "Generate a payment link for the customer for full or permitted partial payment.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "amount_inr": {
                            "type": "number",
                            "description": "The amount in INR for the payment link.",
                        }
                    },
                },
            },
        }
    ]

    return {
        "name": name,
        "voice": {
            "provider": "11labs",
            "voiceId": settings.elevenlabs_voice_id,
            "model": settings.elevenlabs_model,
        },
        "model": {
            "provider": vapi_provider,
            "model": model_name,
            "systemPrompt": system_prompt,
            "messages": [
                {"role": "system", "content": system_prompt}
            ],
            "tools": tools,
        },
        "firstMessage": first_message,
        "maxDurationSeconds": 180,
    }
