import hashlib
import hmac
import json

import pytest

from application .settings import settings
from application .constants import FailureClass
from application .entities import AuditTrail ,TransactionState

WEBHOOK_SECRET ="whsec_test_secret"


@pytest .fixture (autouse =True )
def _set_webhook_secret (monkeypatch ):
    monkeypatch .setattr (settings ,"razorpay_webhook_secret",WEBHOOK_SECRET )


def _sign (body :bytes )->str :
    return hmac .new (WEBHOOK_SECRET .encode (),body ,hashlib .sha256 ).hexdigest ()


def _payment_failed_body (error_code ="ISSUER_DOWN",txn_id ="txn_123"):
    return json .dumps (
    {
    "event":"payment.failed",
    "payload":{
    "payment":{
    "entity":{
    "id":"pay_123",
    "amount":150000 ,
    "currency":"INR",
    "error_code":error_code ,
    "contact":"+919999999999",
    "notes":{"merchant_id":"merch_1","transaction_id":txn_id },
    }
    }
    },
    }
    ).encode ()


def _post (client ,body ,event_id ="evt_123",signature =None ):
    headers ={
    "X-Razorpay-Signature":signature if signature is not None else _sign (body ),
    "X-Razorpay-Event-Id":event_id ,
    "Content-Type":"application/json",
    }
    return client .post ("/api/v1/webhooks/razorpay",content =body ,headers =headers )


def test_valid_webhook_persists_transaction_and_audit (client ,db_session ):
    resp =_post (client ,_payment_failed_body ())
    assert resp .status_code ==200

    txn =db_session .query (TransactionState ).filter_by (transaction_id ="txn_123").one ()
    assert txn .failure_class ==FailureClass .REALTIME_DEGRADATION
    assert txn .razorpay_payment_id =="pay_123"
    assert txn .amount_minor ==150000

    audits =db_session .query (AuditTrail ).filter_by (transaction_id ="txn_123").all ()
    assert any (a .payload .get ("event")=="WEBHOOK_INGESTED"for a in audits )


def test_webhook_kicks_off_orchestration (client ,db_session ):
    resp =_post (client ,_payment_failed_body (),event_id ="evt_orch")
    assert resp .status_code ==200

    assert resp .json ()["current_state"]=="INTERVENING"

    audits =db_session .query (AuditTrail ).filter_by (transaction_id ="txn_123").all ()
    node_names ={a .node_name for a in audits }
    from application .constants import NodeName

    assert NodeName .DIAGNOSE in node_names
    assert NodeName .EXECUTE_INTERVENTION in node_names


def test_invalid_signature_is_rejected_and_persists_nothing (client ,db_session ):
    resp =_post (client ,_payment_failed_body (),signature ="deadbeef")
    assert resp .status_code ==401
    assert db_session .query (TransactionState ).count ()==0


def test_duplicate_event_id_is_not_reprocessed (client ,db_session ):
    body =_payment_failed_body ()
    first =_post (client ,body ,event_id ="evt_dup")
    second =_post (client ,body ,event_id ="evt_dup")

    assert first .status_code ==200
    assert second .status_code ==200
    assert second .json ()["status"]=="duplicate"

    assert db_session .query (TransactionState ).count ()==1
    ingest_audits =[
    a
    for a in db_session .query (AuditTrail ).all ()
    if a .payload .get ("event")=="WEBHOOK_INGESTED"
    ]
    assert len (ingest_audits )==1


def test_invoice_overdue_routes_to_b2b (client ,db_session ):
    body =json .dumps (
    {
    "event":"invoice.overdue",
    "payload":{
    "invoice":{
    "entity":{
    "id":"inv_1",
    "amount":500000 ,
    "currency":"INR",
    "notes":{
    "merchant_id":"merch_1",
    "contact":"+919888888888",
    "transaction_id":"txn_inv",
    },
    }
    }
    },
    }
    ).encode ()
    resp =_post (client ,body ,event_id ="evt_inv")
    assert resp .status_code ==200

    txn =db_session .query (TransactionState ).filter_by (transaction_id ="txn_inv").one ()
    assert txn .failure_class ==FailureClass .B2B_RECEIVABLES
