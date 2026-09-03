"""Deterministic mapping from gateway signals to the four recovery failure classes."""

from application .constants import FailureClass


_ERROR_CODE_TO_CLASS :dict [str ,FailureClass ]={
"BAD_REQUEST_GATEWAY_TIMEOUT":FailureClass .REALTIME_DEGRADATION ,
"GATEWAY_TIMEOUT":FailureClass .REALTIME_DEGRADATION ,
"ISSUER_DOWN":FailureClass .REALTIME_DEGRADATION ,
"NETWORK_FAILURE":FailureClass .REALTIME_DEGRADATION ,
"AUTH_3DS_DROPPED":FailureClass .CHECKOUT_ABANDONMENT ,
"CUSTOMER_AUTH_TIMEOUT":FailureClass .CHECKOUT_ABANDONMENT ,
"SESSION_EXPIRED":FailureClass .CHECKOUT_ABANDONMENT ,
"CUSTOMER_DROPPED_OFF":FailureClass .CHECKOUT_ABANDONMENT ,
"INSUFFICIENT_FUNDS":FailureClass .SUBSCRIPTION_MANDATE ,
"MANDATE_PAUSED":FailureClass .SUBSCRIPTION_MANDATE ,
"TOKEN_EXPIRED":FailureClass .SUBSCRIPTION_MANDATE ,
"MANDATE_REJECTED":FailureClass .SUBSCRIPTION_MANDATE ,
}



_INVOICE_OVERDUE_EVENT ="invoice.overdue"


class UnclassifiableSignal (Exception ):
    """Raised when a webhook carries no signal we can route on.

    Surfacing this loudly (rather than silently defaulting to a class) means an
    unrecognised failure is escalated for a human to look at instead of being
    quietly mis-recovered.
    """


def classify (event_type :str ,error_code :str |None )->FailureClass :
    if event_type ==_INVOICE_OVERDUE_EVENT :
        return FailureClass .B2B_RECEIVABLES

    if error_code :
        mapped =_ERROR_CODE_TO_CLASS .get (error_code .upper ())
        if mapped is not None :
            return mapped

    raise UnclassifiableSignal (
    f"No failure class for event_type={event_type !r } error_code={error_code !r }"
    )
