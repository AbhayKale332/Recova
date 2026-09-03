"""Grounded AI message drafting with a personalized offline template fallback."""

from __future__ import annotations

import logging
from typing import Callable

from sqlalchemy .orm import Session

from application .entities import Message ,TransactionState

logger =logging .getLogger (__name__ )

GenerateFn =Callable [[str ],str ]

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
generate :GenerateFn |None =None ,
locale :str ="en",
)->str :
    txn =(
    db .query (TransactionState )
    .filter_by (transaction_id =transaction_id )
    .one_or_none ()
    )
    if txn is None :
        raise ValueError (f"Unknown transaction: {transaction_id !r }")

    name ,problem ,summary =_context (db ,txn )
    full_prompt =(
    "You are a polite payment-recovery agent messaging a customer on WhatsApp.\n"
    f"Customer: {name }\n"
    f"Situation: {problem }.\n"
    f"Conversation so far:\n{summary }\n\n"
    f"Operator instruction: {prompt }\n\n"
    "Write ONE short, warm, professional WhatsApp message (max 2 sentences). "
    "No preamble, no quotes — just the message text."
    )
    if locale =="hi":
        full_prompt +="\nWrite the message in Hindi (Devanagari script)."

    gen =generate or _default_generate ()
    if gen is not None :
        try :
            text =gen (full_prompt ).strip ().strip ('"')
            if text :
                return text
        except Exception as exc :
            logger .warning ("Message drafting failed (%s); using the standard template.",exc )

    return _fallback (txn ,prompt ,locale )


def _default_generate ()->GenerateFn |None :
    """Build the live text generator lazily; None if the SDK can't be wired."""
    try :
        from application .operations .ai_client import build_text_generate

        return build_text_generate ()
    except Exception :
        return None
