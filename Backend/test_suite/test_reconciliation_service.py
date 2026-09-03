from application .constants import FailureClass ,StoppingRule ,TransactionLifecycleState
from application .entities import EscalationQueue ,TransactionState
from application .operations .reconciliation_service import compute_metrics


def _txn (db ,tid ,failure_class ,amount_minor ,state ):
    db .add (
    TransactionState (
    transaction_id =tid ,
    razorpay_payment_id ="pay_"+tid ,
    failure_class =failure_class ,
    current_state =state ,
    merchant_id ="merch_1",
    customer_contact ="+919999999999",
    amount_minor =amount_minor ,
    )
    )


def _seed_batch (db ):
    _txn (db ,"A",FailureClass .REALTIME_DEGRADATION ,100000 ,TransactionLifecycleState .RECOVERED )
    _txn (db ,"B",FailureClass .CHECKOUT_ABANDONMENT ,200000 ,TransactionLifecycleState .INTERVENING )
    _txn (db ,"C",FailureClass .SUBSCRIPTION_MANDATE ,300000 ,TransactionLifecycleState .CANCELLED )
    _txn (db ,"D",FailureClass .B2B_RECEIVABLES ,400000 ,TransactionLifecycleState .ESCALATED )
    db .add (EscalationQueue (transaction_id ="D",reason ="dispute",rule =StoppingRule .DISPUTE_FREEZE ))
    db .commit ()


def test_grrr_and_totals (db_session ):
    _seed_batch (db_session )
    m =compute_metrics (db_session )


    assert m ["at_risk_inr"]==10000.0
    assert m ["recovered_inr"]==1000.0
    assert round (m ["grrr"],3 )==0.1


def test_state_counts (db_session ):
    _seed_batch (db_session )
    counts =compute_metrics (db_session )["counts"]

    assert counts ["recovered"]==1
    assert counts ["cancelled"]==1
    assert counts ["escalations"]==1


def test_per_class_breakdown (db_session ):
    _seed_batch (db_session )
    by_class =compute_metrics (db_session )["by_class"]

    assert by_class ["1"]["recovered_inr"]==1000.0
    assert by_class ["4"]["at_risk_inr"]==4000.0

    assert set (by_class .keys ())=={"1","2","3","4"}


def test_empty_batch_has_zero_grrr (db_session ):
    m =compute_metrics (db_session )
    assert m ["at_risk_inr"]==0.0
    assert m ["grrr"]==0.0
