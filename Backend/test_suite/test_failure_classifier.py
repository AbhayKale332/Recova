import pytest

from application .constants import FailureClass
from application .operations .failure_classifier import UnclassifiableSignal ,classify


@pytest .mark .parametrize (
"error_code, expected",
[
("BAD_REQUEST_GATEWAY_TIMEOUT",FailureClass .REALTIME_DEGRADATION ),
("ISSUER_DOWN",FailureClass .REALTIME_DEGRADATION ),
("NETWORK_FAILURE",FailureClass .REALTIME_DEGRADATION ),
("AUTH_3DS_DROPPED",FailureClass .CHECKOUT_ABANDONMENT ),
("SESSION_EXPIRED",FailureClass .CHECKOUT_ABANDONMENT ),
("CUSTOMER_DROPPED_OFF",FailureClass .CHECKOUT_ABANDONMENT ),
("INSUFFICIENT_FUNDS",FailureClass .SUBSCRIPTION_MANDATE ),
("TOKEN_EXPIRED",FailureClass .SUBSCRIPTION_MANDATE ),
("MANDATE_REJECTED",FailureClass .SUBSCRIPTION_MANDATE ),
],
)
def test_error_code_routes_to_expected_class (error_code ,expected ):
    assert classify (event_type ="payment.failed",error_code =error_code )==expected


def test_invoice_overdue_event_routes_to_b2b_receivables ():

    assert (
    classify (event_type ="invoice.overdue",error_code =None )
    ==FailureClass .B2B_RECEIVABLES
    )


def test_classification_is_case_insensitive_on_error_code ():
    assert (
    classify (event_type ="payment.failed",error_code ="issuer_down")
    ==FailureClass .REALTIME_DEGRADATION
    )


def test_unknown_signal_raises ():
    with pytest .raises (UnclassifiableSignal ):
        classify (event_type ="payment.failed",error_code ="SOMETHING_NEW")
