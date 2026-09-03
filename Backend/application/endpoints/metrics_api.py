"""Endpoints that expose recovery metrics and human-escalation queue state."""

from fastapi import APIRouter ,Depends ,HTTPException ,status
from sqlalchemy .orm import Session

from application .persistence import get_db
from application .constants import EscalationStatus
from application .entities import EscalationQueue
from application .operations .reconciliation_service import compute_metrics

router =APIRouter (tags =["metrics"])


@router .get ("/metrics")
def get_metrics (db :Session =Depends (get_db ))->dict :
    return compute_metrics (db )


@router .post ("/escalations/{ticket_id}/resolve")
def resolve_escalation (ticket_id :int ,db :Session =Depends (get_db ))->dict :
    """Operator closes a human-handoff ticket."""
    ticket =db .query (EscalationQueue ).filter_by (id =ticket_id ).one_or_none ()
    if ticket is None :
        raise HTTPException (status_code =status .HTTP_404_NOT_FOUND ,detail ="Escalation not found")
    ticket .status =EscalationStatus .RESOLVED
    db .commit ()
    return {
    "id":ticket .id ,
    "transaction_id":ticket .transaction_id ,
    "status":ticket .status .value ,
    }


@router .get ("/escalations")
def get_escalations (db :Session =Depends (get_db ))->list [dict ]:
    tickets =db .query (EscalationQueue ).order_by (EscalationQueue .created_at .desc ()).all ()
    return [
    {
    "id":t .id ,
    "transaction_id":t .transaction_id ,
    "reason":t .reason ,
    "rule":t .rule .value if t .rule else None ,
    "status":t .status .value ,
    "created_at":t .created_at .isoformat (),
    }
    for t in tickets
    ]
