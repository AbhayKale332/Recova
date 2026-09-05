"""Grounded AI message drafting with a personalized offline template fallback."""

from __future__ import annotations

import logging
from typing import Callable

from sqlalchemy .orm import Session

from application .entities import Message ,TransactionState

logger =logging .getLogger (__name__ )

GenerateFn =Callable [[str ],str ]
_ROUTED =object ()

_CLASS_PROBLEM ={
1 :"a real-time payment failure (a gateway/rail glitch on our side)",
2 :"an abandoned checkout (dropped at the OTP/3DS step)",
3 :"a failed subscription auto-debit (low balance before salary)",
4 :"an overdue B2B invoice",
}


def _context (db :Session ,txn :TransactionState )->tuple [str ,str ]:
    name =(txn .metadata_json or {}).get ("customer_name","the customer")
    problem =_CLASS_PROBLEM .get (int (txn .failure_class ),"a payment at risk")
    history =(
    db .query (Message )
    .filter_by (transaction_id =txn .transaction_id )
    .order_by (Message .seq .desc ())
    .limit (6 )
    .all ()
    )
    history .reverse ()
    summary ="\n".join (f"{m .sender .value }: {m .body }"for m in history )or "(no messages yet)"
    return name ,problem ,summary


def _fallback (txn :TransactionState ,prompt :str ,locale :str ="en")->str :
    name =str ((txn .metadata_json or {}).get ("customer_name","there")).split ()[0 ]
    amount =f"₹{int (txn .amount_minor /100 ):,}"
    link =f"rzp.io/i/{txn .transaction_id [-6 :]}"
    if locale =="hi":
        return (
        f"नमस्ते {name }, आपके {amount } के लंबित भुगतान के बारे में याद दिला रहे हैं। "
        f"आप इसे यहाँ सुरक्षित रूप से पूरा कर सकते हैं: {link }। धन्यवाद!"
        )
    return (
    f"Hi {name }, following up regarding your pending {amount } payment. "
    f"You can complete it securely here: {link }. Thank you!"
    )


def draft_message (
db :Session ,
transaction_id :str ,
prompt :str ,
*,
generate :GenerateFn |None |object =_ROUTED ,
locale :str ="en",
)->str :
    txn =(
    db .query (TransactionState )
    .filter_by (transaction_id =transaction_id )
    .one_or_none ()
    )
    if txn is None :
        raise ValueError (f"Unknown transaction: {transaction_id !r }")

    from application.operations import policy_repository

    policy = policy_repository.get_policy(db)
    allow_partial = bool(policy.get("allow_partial_payment", True))
    min_partial_pct = int(policy.get("min_partial_payment_pct", 50))
    amount_inr = float(txn.amount_minor) / 100
    min_partial_inr = amount_inr * (min_partial_pct / 100)

    name ,problem ,summary =_context (db ,txn )
    full_prompt =(
    "You are a polite payment-recovery agent messaging a customer on WhatsApp.\n"
    f"Customer: {name }\n"
    f"Situation: {problem }.\n"
    f"Conversation so far:\n{summary }\n\n"
    f"Merchant Policy & Guardrails:\n"
    f"- Total amount due: ₹{amount_inr:,.2f}\n"
    f"- Partial payments permitted: {'YES' if allow_partial else 'NO'}\n"
    f"- Minimum partial payment allowed: {min_partial_pct}% (₹{min_partial_inr:,.2f})\n"
    f"- Maximum discount cap: {policy.get('max_discount_pct', 0)}%\n\n"
    f"CRITICAL RULES (CHECK PERMISSIONS BEFORE SAYING ANYTHING):\n"
    f"1. You MUST check the merchant policy above before agreeing to, proposing, or discussing any partial payment or installment.\n"
    f"2. If partial payments permitted is NO: Politely refuse any partial payment request, state that policy requires the full payment of ₹{amount_inr:,.2f}, and ask for full payment. Never agree to a partial payment.\n"
    f"3. If partial payments permitted is YES: Any partial payment MUST be at least {min_partial_pct}% of total amount (₹{min_partial_inr:,.2f}). If the customer offers less, refuse the lower amount, explain that policy requires at least {min_partial_pct}% (₹{min_partial_inr:,.2f}), and ask if they can pay ₹{min_partial_inr:,.2f}. Only if the customer offers at least {min_partial_pct}% may you agree to generate a partial payment link.\n\n"
    f"Operator instruction: {prompt }\n\n"
    "Write ONE short, warm, professional WhatsApp message (max 2 sentences). "
    "No preamble, no quotes — just the message text."
    )
    if locale =="hi":
        full_prompt +="\nWrite the message in Hindi (Devanagari script)."

    # Convert paise to rupees once, at the router boundary.
    if generate is _ROUTED:
        gen =_default_generate (txn .amount_minor /100 )
    else:
        # ``None`` is an intentional offline instruction used by batch paths.
        gen =generate
    if gen is not None :
        try :
            text =gen (full_prompt ).strip ().strip ('"')
            if text :
                return text
        except Exception as exc :
            logger .warning ("Message drafting failed (%s); using the standard template.",exc )

    return _fallback (txn ,prompt ,locale )


def _default_generate (amount_inr :float =0 )->GenerateFn |None :
    """Build the live text generator lazily; None if the SDK can't be wired."""
    try :
        from application .operations .model_router import build_task_generate

        return build_task_generate ("DRAFT",amount_inr =amount_inr ,live =True )
    except Exception :
        return None
