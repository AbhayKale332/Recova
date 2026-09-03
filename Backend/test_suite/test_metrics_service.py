from application .constants import FailureClass ,StoppingRule ,TransactionLifecycleState
from application .entities import EscalationQueue ,TransactionState


def _seed (db ):
    db .add (
    TransactionState (
    transaction_id ="M1",
    razorpay_payment_id ="pay_M1",
    failure_class =FailureClass .REALTIME_DEGRADATION ,
    current_state =TransactionLifecycleState .RECOVERED ,
    merchant_id ="merch_1",
    customer_contact ="+919999999999",
    amount_minor =100000 ,
    )
    )
    db .add (EscalationQueue (transaction_id ="M1",reason ="needs a human",rule =StoppingRule .DISPUTE_FREEZE ))
    db .commit ()


def test_metrics_endpoint_returns_grrr (client ,db_session ):
    _seed (db_session )
    resp =client .get ("/api/v1/metrics")
    assert resp .status_code ==200
    body =resp .json ()
    assert body ["recovered_inr"]==1000.0
    assert body ["grrr"]==1.0
    assert "by_class"in body


def test_escalations_endpoint_lists_tickets (client ,db_session ):
    _seed (db_session )
    resp =client .get ("/api/v1/escalations")
    assert resp .status_code ==200
    tickets =resp .json ()
    assert len (tickets )==1
    assert tickets [0 ]["transaction_id"]=="M1"
    assert tickets [0 ]["rule"]=="DISPUTE_FREEZE"
    assert tickets [0 ]["status"]=="OPEN"
