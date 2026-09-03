"""Class-3 subscription calendar and Class-4 receivables board."""

from datetime import date

from application .constants import FailureClass ,TransactionLifecycleState
from application .entities import TransactionState
from application .operations .tracker_service import list_invoices ,list_subscriptions
from application .helpers import utcnow


def _txn (db ,fc ,name ,state =TransactionLifecycleState .PENDING ,amount =499900 ,meta =None ):
    t =TransactionState (
    transaction_id =f"txn_{int (fc )}_{name }",
    razorpay_payment_id =f"pay_{name }",
    failure_class =int (fc ),
    current_state =state ,
    merchant_id ="m",
    customer_contact ="+919900000000",
    amount_minor =amount ,
    metadata_json ={"customer_name":name ,"is_at_risk":True ,**(meta or {})},
    )
    db .add (t )
    db .commit ()
    return t




def test_list_subscriptions_only_class_3 (db_session ):
    _txn (db_session ,FailureClass .SUBSCRIPTION_MANDATE ,"Sub")
    _txn (db_session ,FailureClass .B2B_RECEIVABLES ,"Inv")
    subs =list_subscriptions (db_session )
    assert [s ["customer_name"]for s in subs ]==["Sub"]
    s =subs [0 ]
    assert s ["next_debit_date"]and s ["retry_cap"]==3
    assert s ["predicted_fail"]is True


def test_recovered_items_never_sit_on_a_future_date (db_session ):


    today =utcnow ().date ()
    _txn (db_session ,FailureClass .SUBSCRIPTION_MANDATE ,"PaidSub",
    state =TransactionLifecycleState .RECOVERED )
    _txn (db_session ,FailureClass .B2B_RECEIVABLES ,"PaidInv",
    state =TransactionLifecycleState .RECOVERED )
    sub =list_subscriptions (db_session )[0 ]
    inv =list_invoices (db_session )[0 ]
    assert sub ["mandate_status"]=="recovered"
    assert date .fromisoformat (sub ["next_debit_date"])<today
    assert date .fromisoformat (inv ["due_date"])<today


def test_pending_subscription_debit_is_upcoming (db_session ):
    today =utcnow ().date ()
    _txn (db_session ,FailureClass .SUBSCRIPTION_MANDATE ,"Upcoming",
    state =TransactionLifecycleState .PENDING )
    assert date .fromisoformat (list_subscriptions (db_session )[0 ]["next_debit_date"])>=today


def test_waiting_subscription_reads_as_deferred (db_session ):
    _txn (db_session ,FailureClass .SUBSCRIPTION_MANDATE ,"Salary",
    state =TransactionLifecycleState .WAITING )
    assert list_subscriptions (db_session )[0 ]["mandate_status"]=="deferred"


def test_add_subscription_endpoint_creates_runnable_case (client ,db_session ):
    resp =client .post ("/api/v1/subscriptions",json ={
    "customer_name":"Nayantara","plan":"Rooh Pro","amount_inr":799 ,
    "next_debit_date":"2026-09-05","salary_day":1 ,
    })
    assert resp .status_code ==200
    body =resp .json ()
    assert body ["plan"]=="Rooh Pro"
    assert body ["next_debit_date"]=="2026-09-05"

    row =db_session .query (TransactionState ).filter_by (transaction_id =body ["transaction_id"]).one ()
    assert int (row .failure_class )==int (FailureClass .SUBSCRIPTION_MANDATE )
    assert row .current_state ==TransactionLifecycleState .PENDING




def test_invoice_aging_buckets (db_session ):
    _txn (db_session ,FailureClass .B2B_RECEIVABLES ,"Old",
    meta ={"due_date":"2000-01-01"})
    _txn (db_session ,FailureClass .B2B_RECEIVABLES ,"Future",
    meta ={"due_date":"2999-01-01"})
    by_name ={i ["buyer_name"]:i for i in list_invoices (db_session )}
    assert by_name ["Old"]["aging_bucket"]=="90+"
    assert by_name ["Future"]["aging_bucket"]=="current"


def test_invoice_p2p_drives_next_reminder (db_session ):
    _txn (db_session ,FailureClass .B2B_RECEIVABLES ,"Promised",
    meta ={"due_date":"2026-07-31","p2p_date":"2026-09-05"})
    inv =list_invoices (db_session )[0 ]
    assert inv ["p2p_date"]=="2026-09-05"
    assert inv ["next_reminder_date"]=="2026-09-05"


def test_add_invoice_endpoint_creates_runnable_case (client ,db_session ):
    resp =client .post ("/api/v1/invoices",json ={
    "buyer_name":"Acme Corp","amount_inr":84000 ,
    "issue_date":"2026-07-01","due_date":"2026-07-31",
    })
    assert resp .status_code ==200
    body =resp .json ()
    assert body ["buyer_name"]=="Acme Corp"
    assert body ["due_date"]=="2026-07-31"
    row =db_session .query (TransactionState ).filter_by (transaction_id =body ["transaction_id"]).one ()
    assert int (row .failure_class )==int (FailureClass .B2B_RECEIVABLES )
