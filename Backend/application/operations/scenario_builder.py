"""Synthetic failure scenario builder for deterministic recovery demonstrations."""

import uuid
from dataclasses import dataclass

from application .constants import FailureClass
from application .workflow .workflow_state import RecoveryState
from application .entities import TransactionState

_DEMO_CONTACT ="+919900000000"
_DEMO_MERCHANT ="merch_demo"


@dataclass
class SyntheticScenario :
    transaction_id :str
    failure_class :FailureClass
    event_type :str
    error_code :str |None
    amount_minor :int
    currency :str
    merchant_id :str
    customer_contact :str
    outcome_event :str |None

    def to_transaction_state (self )->TransactionState :
        return TransactionState (
        transaction_id =self .transaction_id ,
        razorpay_payment_id =f"pay_{self .transaction_id }",
        failure_class =int (self .failure_class ),
        merchant_id =self .merchant_id ,
        customer_contact =self .customer_contact ,
        amount_minor =self .amount_minor ,
        currency =self .currency ,
        )

    def to_initial_state (self )->RecoveryState :
        return {
        "transaction_id":self .transaction_id ,
        "failure_class":int (self .failure_class ),
        "telemetry":{"event_type":self .event_type ,"error_code":self .error_code },
        "outcome_event":self .outcome_event ,
        }



_TEMPLATES :dict [FailureClass ,tuple [str ,str |None ,int ]]={
FailureClass .REALTIME_DEGRADATION :("payment.failed","ISSUER_DOWN",249900 ),
FailureClass .CHECKOUT_ABANDONMENT :("payment.failed","AUTH_3DS_DROPPED",149900 ),
FailureClass .SUBSCRIPTION_MANDATE :("payment.failed","INSUFFICIENT_FUNDS",89900 ),
FailureClass .B2B_RECEIVABLES :("invoice.overdue",None ,8400000 ),
}


def synthesize (failure_class ,recovered :bool =True )->SyntheticScenario :
    try :
        fc =FailureClass (failure_class )
    except ValueError as exc :
        raise ValueError (f"Unknown failure class: {failure_class !r }")from exc

    event_type ,error_code ,amount_minor =_TEMPLATES [fc ]
    return SyntheticScenario (
    transaction_id =f"demo_{int (fc )}_{uuid .uuid4 ().hex [:8 ]}",
    failure_class =fc ,
    event_type =event_type ,
    error_code =error_code ,
    amount_minor =amount_minor ,
    currency ="INR",
    merchant_id =_DEMO_MERCHANT ,
    customer_contact =_DEMO_CONTACT ,
    outcome_event ="payment.captured"if recovered else None ,
    )
