"""Maps approved recovery actions to the correct external adapter and channel."""

from typing import Callable

from sqlalchemy .orm import Session

from application .integrations .adapter_base import DispatchResult
from application .integrations .payment_actions import RazorpayActionsAdapter
from application .integrations .voice_gateway import VoiceAdapter
from application .integrations .messaging_gateway import WhatsAppAdapter
from application .settings import settings
from application .constants import InterventionAction
from application .entities import TransactionState
from application .operations .policy_guard import ProposedAction



# Adapter messages are centralized here so channel wording stays consistent across playbooks.
_WHATSAPP_BODY ="We identified a technical issue while processing your payment. To continue, please use the secure payment link below."
_VOICE_SCRIPT ="maaf kijiye, aapke payment process mein takniki samasya aa gayi thi. payment jaari rakhne ke liye, kripya neeche diye gaye link par click karein."


def build_dispatcher (db :Session ,live_mode :bool |None =None )->Callable [[ProposedAction ,dict ],DispatchResult ]:
    # The mode is resolved once and shared by every adapter in this dispatcher.
    live =settings .live_mode if live_mode is None else live_mode
    whatsapp =WhatsAppAdapter (live_mode =live )
    voice =VoiceAdapter (live_mode =live )
    razorpay =RazorpayActionsAdapter (live_mode =live )

    def dispatch (action :ProposedAction ,state :dict )->DispatchResult :
        txn =(
        db .query (TransactionState )
        .filter_by (transaction_id =state ["transaction_id"])
        .one ()
        )
        to =txn .customer_contact
        amount =action .amount_minor or txn .amount_minor

        # The policy gate runs before dispatch; this match only selects the approved adapter.
        match action .action_value :
            case InterventionAction .SEND_WHATSAPP .value |InterventionAction .OFFER_FEE_WAIVER .value :
                return whatsapp .send (to =to ,body =_WHATSAPP_BODY )
            case InterventionAction .VOICE_CALL .value :
                return voice .call (to =to ,script =_VOICE_SCRIPT )
            case InterventionAction .GENERATE_PAYMENT_LINK .value :
                return razorpay .create_payment_link (amount_minor =amount ,contact =to )
            case InterventionAction .RETRY_CHARGE .value :
                return razorpay .retry_charge (transaction_id =txn .transaction_id )
            case InterventionAction .CANCEL_SUBSCRIPTION .value :
                return razorpay .cancel_subscription (transaction_id =txn .transaction_id )
            case other :
                raise ValueError (f"No dispatcher route for action {other !r }")

    return dispatch
