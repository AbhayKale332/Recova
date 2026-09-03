import pytest

from application .constants import FailureClass
from application .operations .scenario_builder import synthesize


def test_each_class_has_distinct_trigger ():
    codes ={}
    for fc in FailureClass :
        s =synthesize (fc )
        codes [int (fc )]=(s .event_type ,s .error_code )

    assert codes [1 ][1 ]=="ISSUER_DOWN"
    assert codes [2 ][1 ]=="AUTH_3DS_DROPPED"
    assert codes [3 ][1 ]=="INSUFFICIENT_FUNDS"
    assert codes [4 ][0 ]=="invoice.overdue"
    assert codes [4 ][1 ]is None


def test_scenario_is_well_formed ():
    s =synthesize (FailureClass .REALTIME_DEGRADATION )
    assert s .failure_class ==FailureClass .REALTIME_DEGRADATION
    assert s .transaction_id .startswith ("demo_")
    assert s .amount_minor >0
    assert s .customer_contact .startswith ("+")


def test_recovered_flag_controls_outcome_event ():
    assert synthesize (FailureClass .REALTIME_DEGRADATION ,recovered =True ).outcome_event =="payment.captured"
    assert synthesize (FailureClass .REALTIME_DEGRADATION ,recovered =False ).outcome_event is None


def test_transaction_ids_are_unique ():
    a =synthesize (FailureClass .CHECKOUT_ABANDONMENT )
    b =synthesize (FailureClass .CHECKOUT_ABANDONMENT )
    assert a .transaction_id !=b .transaction_id


def test_unknown_class_rejected ():
    with pytest .raises (ValueError ):
        synthesize (9 )
