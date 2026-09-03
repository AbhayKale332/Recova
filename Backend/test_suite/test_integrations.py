from application .integrations .adapter_base import DispatchResult
from application .integrations .routing_dispatcher import build_dispatcher
from application .integrations .payment_actions import RazorpayActionsAdapter
from application .integrations .voice_gateway import VoiceAdapter
from application .integrations .messaging_gateway import WhatsAppAdapter
from application .constants import (
FailureClass ,
InterventionAction ,
InterventionChannel ,
TransactionLifecycleState ,
)
from application .entities import TransactionState
from application .operations .policy_guard import ProposedAction





def test_whatsapp_sim_does_not_call_network ():
    adapter =WhatsAppAdapter (live_mode =False )
    result =adapter .send (to ="+919999999999",body ="hi")
    assert isinstance (result ,DispatchResult )
    assert result .simulated is True
    assert result .delivered is True
    assert result .channel =="WHATSAPP"


def test_whatsapp_live_failure_degrades_gracefully ():


    class _BoomClient :
        class messages :
            @staticmethod
            def create (**kwargs ):
                raise RuntimeError ("Twilio 400: ContentSid Required")

    adapter =WhatsAppAdapter (live_mode =True ,client =_BoomClient ())
    result =adapter .send (to ="+919999999999",body ="hi")
    assert result .delivered is False
    assert result .simulated is False
    assert result .detail is not None


def test_voice_stays_simulated_without_vapi_key ():

    adapter =VoiceAdapter (live_mode =True ,api_key ="")
    result =adapter .call (to ="+919999999999",script ="namaste")
    assert result .simulated is True
    assert result .channel =="VOICE"


def test_razorpay_sim_payment_link_has_reference ():
    adapter =RazorpayActionsAdapter (live_mode =False )
    result =adapter .create_payment_link (amount_minor =150000 ,contact ="+919999999999")
    assert result .simulated is True
    assert result .reference is not None
    assert result .channel =="PAYMENT_LINK"





def _seed (db ,transaction_id ="txn_disp1"):
    db .add (
    TransactionState (
    transaction_id =transaction_id ,
    razorpay_payment_id ="pay_x",
    failure_class =FailureClass .CHECKOUT_ABANDONMENT ,
    current_state =TransactionLifecycleState .INTERVENING ,
    merchant_id ="merch_1",
    customer_contact ="+919999999999",
    amount_minor =150000 ,
    )
    )
    db .commit ()
    return transaction_id


def test_dispatcher_routes_whatsapp (db_session ):
    txn_id =_seed (db_session )
    dispatch =build_dispatcher (db_session ,live_mode =False )
    result =dispatch (
    ProposedAction (action =InterventionAction .SEND_WHATSAPP ,channel =InterventionChannel .WHATSAPP ),
    {"transaction_id":txn_id },
    )
    assert result .channel =="WHATSAPP"
    assert result .simulated is True


def test_dispatcher_routes_payment_link (db_session ):
    txn_id =_seed (db_session ,"txn_disp2")
    dispatch =build_dispatcher (db_session ,live_mode =False )
    result =dispatch (
    ProposedAction (
    action =InterventionAction .GENERATE_PAYMENT_LINK ,
    channel =InterventionChannel .PAYMENT_LINK ,
    amount_minor =150000 ,
    ),
    {"transaction_id":txn_id },
    )
    assert result .channel =="PAYMENT_LINK"
    assert result .reference is not None


def test_dispatcher_routes_voice (db_session ):
    txn_id =_seed (db_session ,"txn_disp3")
    dispatch =build_dispatcher (db_session ,live_mode =False )
    result =dispatch (
    ProposedAction (action =InterventionAction .VOICE_CALL ,channel =InterventionChannel .VOICE ),
    {"transaction_id":txn_id },
    )
    assert result .channel =="VOICE"
    assert result .simulated is True
