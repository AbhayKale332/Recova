"""Bookkeeping for simulation runs: listing, replaying, and pruning them.

Simulated cases share the real tables - the engine is real, so the audit trail
they leave is real evidence and belongs with everything else. What separates them
is ``metadata_json.simulation_run_id``, which every read path uses to keep the
merchant's actual numbers clean.

Because runs accumulate on every click, this module also prunes them. Without
that, a demo afternoon leaves thousands of rows behind and the case list slows
down for reasons no one can see.
"""

from __future__ import annotations

from sqlalchemy .orm import Session

from application .entities import (
AuditTrail ,
CallSession ,
CallTurn ,
EscalationQueue ,
Message ,
SavedScenario ,
TransactionState ,
)
from application .operations .reconciliation_service import compute_metrics
from application .helpers import utcnow

# How many finished runs to keep. Enough to compare a couple of scenarios
# side by side; not enough to bloat the file.
KEEP_RUNS =5


def _run_id (txn :TransactionState )->str |None :
    return (txn .metadata_json or {}).get ("simulation_run_id")


def save_scenario (db :Session ,slug :str ,name :str ,description :str ,payload :dict )->dict :
    """Upsert one saved scenario by its shareable slug."""
    saved =db .query (SavedScenario ).filter_by (slug =slug ).one_or_none ()
    if saved is None :
        saved =SavedScenario (slug =slug ,name =name ,description =description ,payload =payload )
        db .add (saved )
    else :
        saved .name =name
        saved .description =description
        saved .payload =payload
        saved .updated_at =utcnow ()
    db .commit ()
    db .refresh (saved )
    return saved .as_dict ()


def list_scenarios (db :Session )->list [dict ]:
    """Saved scenarios, newest edits first."""
    rows =db .query (SavedScenario ).order_by (SavedScenario .updated_at .desc ()).all ()
    return [row .as_dict ()for row in rows ]


def get_scenario (db :Session ,slug :str )->dict |None :
    row =db .query (SavedScenario ).filter_by (slug =slug ).one_or_none ()
    return row .as_dict ()if row else None


def delete_scenario (db :Session ,slug :str )->bool :
    row =db .query (SavedScenario ).filter_by (slug =slug ).one_or_none ()
    if row is None :
        return False
    db .delete (row )
    db .commit ()
    return True


def list_runs (db :Session )->list [dict ]:
    """Every simulation run currently in the database, newest first."""
    runs :dict [str ,dict ]={}
    for txn in db .query (TransactionState ).all ():
        if (txn.metadata_json or {}).get ("live_session_id"):
            # Live sessions have their own in-process lifecycle. Keeping them
            # out of simulation pruning protects their append-only evidence.
            continue
        run_id =_run_id (txn )
        if not run_id :
            continue
        entry =runs .setdefault (run_id ,{"run_id":run_id ,"cases":0 ,"created_at":txn .created_at })
        entry ["cases"]+=1
        entry ["created_at"]=min (entry ["created_at"],txn .created_at )

    ordered =sorted (runs .values (),key =lambda r :r ["created_at"],reverse =True )
    for entry in ordered :
        entry ["created_at"]=entry ["created_at"].isoformat ()
    return ordered


def transaction_ids (db :Session ,run_id :str )->list [str ]:
    return [
    txn .transaction_id
    for txn in db .query (TransactionState ).all ()
    if _run_id (txn )==run_id
    ]


def replay (db :Session ,run_id :str )->dict |None :
    """The finished shape of a run, for reloading it without re-executing."""
    ids =transaction_ids (db ,run_id )
    if not ids :
        return None
    return {"run_id":run_id ,"total":len (ids ),"metrics":compute_metrics (db ,simulation_run_id =run_id )}


def delete_run (db :Session ,run_id :str )->int :
    """Remove one run's rows entirely.

    Audit rows are deleted in bulk, which bypasses the append-only ORM guards.
    That is correct here and only here: these rows describe a hypothetical the
    user asked to discard, not a real recovery anyone is accountable for.
    """
    ids =transaction_ids (db ,run_id )
    if not ids :
        return 0

    calls =[c .id for c in db .query (CallSession ).filter (CallSession .transaction_id .in_ (ids )).all ()]
    if calls :
        db .query (CallTurn ).filter (CallTurn .call_session_id .in_ (calls )).delete (synchronize_session =False )
    db .query (CallSession ).filter (CallSession .transaction_id .in_ (ids )).delete (synchronize_session =False )
    db .query (Message ).filter (Message .transaction_id .in_ (ids )).delete (synchronize_session =False )
    db .query (EscalationQueue ).filter (EscalationQueue .transaction_id .in_ (ids )).delete (synchronize_session =False )
    db .query (AuditTrail ).filter (AuditTrail .transaction_id .in_ (ids )).delete (synchronize_session =False )
    db .query (TransactionState ).filter (TransactionState .transaction_id .in_ (ids )).delete (synchronize_session =False )
    db .commit ()
    return len (ids )


def prune (db :Session ,keep :int =KEEP_RUNS )->list [str ]:
    """Drop all but the newest ``keep`` runs. Returns the run ids removed."""
    stale =[entry ["run_id"]for entry in list_runs (db )[keep :]]
    for run_id in stale :
        delete_run (db ,run_id )
    return stale
