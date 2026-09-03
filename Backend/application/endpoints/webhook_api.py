"""Authenticated Razorpay webhook ingestion with idempotency and recovery orchestration."""

import hashlib
import hmac
from typing import Any

from fastapi import APIRouter ,Depends ,Header ,HTTPException ,Request ,status
from sqlalchemy .orm import Session

from application .settings import settings
from application .persistence import get_db
from application .constants import (
ActionType ,
NodeName ,
Outcome ,
TransactionLifecycleState ,
)
from application .entities import TransactionState
from application .workflow .workflow_factory import get_orchestrator_deps
from application .workflow .recovery_graph import OrchestratorDeps ,build_recovery_graph
from application .operations .audit_service import record_audit
from application .operations .failure_classifier import UnclassifiableSignal ,classify
from application .operations .idempotency_service import claim_event

router =APIRouter (prefix ="/webhooks",tags =["webhooks"])


def _signature_is_valid (raw_body :bytes ,signature :str |None )->bool :
    """Constant-time verification of Razorpay's HMAC-SHA256 body signature."""
    secret =settings .razorpay_webhook_secret
    if not secret or not signature :
        return False
    expected =hmac .new (secret .encode (),raw_body ,hashlib .sha256 ).hexdigest ()
    return hmac .compare_digest (expected ,signature )


def _extract_entity (body :dict [str ,Any ])->dict [str ,Any ]:
    """Pull the domain entity out of Razorpay's ``payload.<type>.entity`` nesting.

    Razorpay wraps the payment/subscription/invoice entity under a type key that
    varies per event, so we take the first wrapper that carries an ``entity``.
    """
    payload =body .get ("payload")or {}
    for wrapper in payload .values ():
        if isinstance (wrapper ,dict )and "entity"in wrapper :
            return wrapper ["entity"]or {}
    return {}


@router .post ("/razorpay")
async def ingest_razorpay_event (
request :Request ,
db :Session =Depends (get_db ),
deps :OrchestratorDeps =Depends (get_orchestrator_deps ),
x_razorpay_signature :str |None =Header (default =None ),
x_razorpay_event_id :str |None =Header (default =None ),
):
    raw_body =await request .body ()

    # Verify authenticity before parsing or persisting the event payload.
    if not _signature_is_valid (raw_body ,x_razorpay_signature ):
        raise HTTPException (
        status_code =status .HTTP_401_UNAUTHORIZED ,
        detail ="Invalid webhook signature.",
        )

    body =await request .json ()
    event_type =body .get ("event","")


    event_id =x_razorpay_event_id or body .get ("id")
    if not event_id :
        raise HTTPException (
        status_code =status .HTTP_400_BAD_REQUEST ,
        detail ="Missing webhook event id.",
        )

    # Duplicate gateway deliveries are acknowledged without executing recovery twice.
    if not claim_event (db ,event_id ):


        return {"status":"duplicate","event_id":event_id }

    entity =_extract_entity (body )
    notes =entity .get ("notes")or {}
    error_code =entity .get ("error_code")

    try :
        failure_class =classify (event_type =event_type ,error_code =error_code )
    except UnclassifiableSignal as exc :
        raise HTTPException (
        status_code =status .HTTP_422_UNPROCESSABLE_ENTITY ,
        detail =str (exc ),
        )

    entity_id =entity .get ("id","")
    transaction_id =notes .get ("transaction_id")or entity_id
    customer_contact =entity .get ("contact")or notes .get ("contact")or ""
    merchant_id =notes .get ("merchant_id")or "unknown"



    txn =(
    db .query (TransactionState )
    .filter_by (transaction_id =transaction_id )
    .one_or_none ()
    )
    if txn is None :
        txn =TransactionState (
        transaction_id =transaction_id ,
        razorpay_payment_id =entity_id ,
        failure_class =int (failure_class ),
        current_state =TransactionLifecycleState .PENDING ,
        merchant_id =merchant_id ,
        customer_contact =customer_contact ,
        amount_minor =entity .get ("amount",0 ),
        currency =entity .get ("currency","INR"),
        )
        db .add (txn )
    else :
        txn .failure_class =int (failure_class )
    db .commit ()

    record_audit (
    db ,
    transaction_id =transaction_id ,
    node_name =NodeName .INGEST ,
    action_type =ActionType .STATE_TRANSITION ,
    payload ={
    "event":"WEBHOOK_INGESTED",
    "event_type":event_type ,
    "error_code":error_code ,
    "failure_class":int (failure_class ),
    },
    outcome =Outcome .SUCCESS ,
    )




    graph =build_recovery_graph (deps )
    graph .invoke (
    {
    "transaction_id":transaction_id ,
    "telemetry":{"event_type":event_type ,"error_code":error_code },
    }
    )

    txn =db .query (TransactionState ).filter_by (transaction_id =transaction_id ).one ()
    return {
    "status":"ingested",
    "transaction_id":transaction_id ,
    "failure_class":int (failure_class ),
    "current_state":txn .current_state .value ,
    }
