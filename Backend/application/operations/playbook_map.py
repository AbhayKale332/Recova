"""Neutral mappings shared by diagnosis, workflow, simulation, and tools.

Keeping these translations in ``operations`` prevents the operations package
from importing workflow implementation details.
"""

from application.constants import FailureClass, InterventionAction, InterventionChannel, Playbook


PLAYBOOK_ACTION: dict[Playbook, tuple[InterventionAction, InterventionChannel | None]] = {
    Playbook.REROUTE_RAIL: (InterventionAction.GENERATE_PAYMENT_LINK, InterventionChannel.PAYMENT_LINK),
    Playbook.PREAUTH_LINK: (InterventionAction.GENERATE_PAYMENT_LINK, InterventionChannel.PAYMENT_LINK),
    Playbook.UPI_AUTOPAY_NUDGE: (InterventionAction.SEND_WHATSAPP, InterventionChannel.WHATSAPP),
    Playbook.NEGOTIATION: (InterventionAction.OFFER_FEE_WAIVER, InterventionChannel.WHATSAPP),
    Playbook.SALARY_CYCLE_SEQUENCER: (InterventionAction.RETRY_CHARGE, None),
    Playbook.MANDATE_REFRESH: (InterventionAction.VOICE_CALL, InterventionChannel.VOICE),
    Playbook.P2P_TRACKER: (InterventionAction.SEND_WHATSAPP, InterventionChannel.WHATSAPP),
}


DEFAULT_PLAYBOOK: dict[FailureClass, Playbook] = {
    FailureClass.REALTIME_DEGRADATION: Playbook.REROUTE_RAIL,
    FailureClass.CHECKOUT_ABANDONMENT: Playbook.UPI_AUTOPAY_NUDGE,
    FailureClass.SUBSCRIPTION_MANDATE: Playbook.SALARY_CYCLE_SEQUENCER,
    FailureClass.B2B_RECEIVABLES: Playbook.P2P_TRACKER,
}


# What each playbook is for, as Jev's diagnosis criteria. Written as the
# situation it fits, so the choice is a judgment about the case, not a lookup.
PLAYBOOK_CRITERIA: dict[Playbook, str] = {
    Playbook.REROUTE_RAIL: (
        "Send a fresh payment link on another rail. Fits a bank, issuer, or network outage "
        "(gateway timeout, issuer down) where the customer wanted to pay."
    ),
    Playbook.PREAUTH_LINK: (
        "Send a pre-authorised payment link. Fits a checkout that dropped during authentication "
        "(3-D Secure or OTP step) or whose session expired."
    ),
    Playbook.UPI_AUTOPAY_NUDGE: (
        "Nudge the customer on WhatsApp to finish a checkout they abandoned or a UPI payment left pending."
    ),
    Playbook.NEGOTIATION: (
        "Offer a concession (fee waiver or discount). Fits a customer who objects to the price or cost."
    ),
    Playbook.SALARY_CYCLE_SEQUENCER: (
        "Retry the auto-debit timed to the customer's salary credit. Fits a mandate that bounced for "
        "insufficient funds or a customer who says money arrives later."
    ),
    Playbook.MANDATE_REFRESH: (
        "Call the customer to re-authorise the mandate. Fits a mandate or card token that is expired, "
        "paused, cancelled, or rejected."
    ),
    Playbook.P2P_TRACKER: (
        "Track a promise to pay by a date. Fits an overdue business invoice, or a customer who commits "
        "to paying on a specific day."
    ),
}


# Closed root-cause vocabulary per class for Jev's diagnosis. The first entry
# of each is the class's seeded default (batch_seed._CLASS_PROFILE); UNKNOWN is
# the no-match option.
ROOT_CAUSES: dict[FailureClass, dict[str, str]] = {
    FailureClass.REALTIME_DEGRADATION: {
        "ISSUER_LATENCY_SPIKE": "The issuing bank responded too slowly or timed out.",
        "ISSUER_DOWN": "The issuing bank was unavailable.",
        "NETWORK_FAILURE": "A network or gateway connection failed.",
        "UNKNOWN": "None of these fits the evidence.",
    },
    FailureClass.CHECKOUT_ABANDONMENT: {
        "OTP_SESSION_EXPIRED": "The OTP or authentication session expired before the customer finished.",
        "AUTH_3DS_DROPPED": "The customer dropped off at the 3-D Secure step.",
        "CUSTOMER_HESITATION": "The customer left on purpose, unsure about the purchase or price.",
        "UNKNOWN": "None of these fits the evidence.",
    },
    FailureClass.SUBSCRIPTION_MANDATE: {
        "SALARY_CYCLE_MISMATCH": "The debit ran before the customer's salary arrived (insufficient funds).",
        "MANDATE_PAUSED": "The customer or bank paused or cancelled the mandate.",
        "TOKEN_EXPIRED": "The card or mandate token expired.",
        "MANDATE_REJECTED": "The bank rejected the mandate.",
        "UNKNOWN": "None of these fits the evidence.",
    },
    FailureClass.B2B_RECEIVABLES: {
        "BUYER_APPROVAL_DELAY": "The invoice is waiting on the buyer's internal approval.",
        "DISPUTE_BREWING": "The buyer questions the invoice, amount, or delivery.",
        "AP_SYSTEM_OUTAGE": "The buyer's accounts-payable system or process is stuck.",
        "CASH_FLOW_CRUNCH": "The buyer is short of cash and delaying payment.",
        "UNKNOWN": "None of these fits the evidence.",
    },
}
