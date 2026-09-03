"""The batch seeder — populates the DB with a realistic, mixed set of
transactions run through the *real* orchestrator, so the dashboard's numbers are
computed rather than asserted."""

from application .constants import FailureClass ,TransactionLifecycleState
from application .entities import AuditTrail ,TransactionState
from application .operations .batch_seed import DEFAULT_BATCH ,seed_batch


def test_seed_bulk_spread_per_class (db_session ):
    from collections import Counter

    from application .operations .batch_seed import _seed_bulk

    _seed_bulk (db_session ,per_class =20 )
    rows =db_session .query (TransactionState ).all ()
    for fc in FailureClass :
        cls =[t for t in rows if int (t .failure_class )==int (fc )]
        assert len (cls )==20
        states =Counter (t .current_state .value for t in cls )
        assert len (states )==5
        assert states ["RECOVERED"]==12

    from application .entities import EscalationQueue

    assert db_session .query (EscalationQueue ).count ()==4 *2


def test_seed_batch_populates_transactions (db_session ):
    result =seed_batch (db_session )
    rows =db_session .query (TransactionState ).all ()

    assert result .seeded ==len (rows )>=sum (s .count for s in DEFAULT_BATCH )
    assert result .seeded >=40


def test_seed_batch_covers_all_four_classes_plus_context (db_session ):
    seed_batch (db_session )
    rows =db_session .query (TransactionState ).all ()
    classes ={int (t .failure_class )for t in rows }
    assert classes =={1 ,2 ,3 ,4 }
    archetypes ={(t .metadata_json or {}).get ("archetype")for t in rows }
    assert "HEALTHY"in archetypes
    assert "NON_RECOVERABLE"in archetypes


def test_all_eight_stopping_rules_fire_in_the_batch (db_session ):

    from application .operations .reconciliation_service import compute_metrics

    seed_batch (db_session )
    fired =compute_metrics (db_session )["stopping_rules_by_name"]
    for rule in ("NO_DOUBLE_CHARGE","CROSS_DEVICE_COMPLETION","RBI_MAX_RETRIES",
    "EXPLICIT_CANCEL","OPT_OUT","DISPUTE_FREEZE",
    "TRAI_QUIET_HOURS","VOICE_ATTEMPT_CAP"):
        assert fired .get (rule ,0 )>=1 ,f"{rule } never fired"


def test_seed_batch_produces_a_spread_of_outcomes (db_session ):
    seed_batch (db_session )
    rows =db_session .query (TransactionState ).all ()
    states ={t .current_state for t in rows }


    assert TransactionLifecycleState .RECOVERED in states
    assert TransactionLifecycleState .INTERVENING in states
    assert TransactionLifecycleState .ESCALATED in states
    assert TransactionLifecycleState .CANCELLED in states


def test_at_risk_cases_flowed_through_the_real_orchestrator (db_session ):
    """Every recovery case leaves a genuine audit trail (ingest→diagnose→…)."""
    seed_batch (db_session )
    at_risk =[
    t
    for t in db_session .query (TransactionState ).all ()
    if (t .metadata_json or {}).get ("is_at_risk")
    ]
    assert at_risk
    for t in at_risk [:5 ]:
        trail =(
        db_session .query (AuditTrail )
        .filter_by (transaction_id =t .transaction_id )
        .count ()
        )
        assert trail >=2


def test_healthy_rows_are_not_at_risk_and_have_no_audit (db_session ):
    seed_batch (db_session )
    healthy =[
    t
    for t in db_session .query (TransactionState ).all ()
    if (t .metadata_json or {}).get ("archetype")=="HEALTHY"
    ]
    assert healthy
    for t in healthy :
        assert (t .metadata_json or {}).get ("is_at_risk")is False
        assert t .current_state ==TransactionLifecycleState .RECOVERED
        assert (
        db_session .query (AuditTrail )
        .filter_by (transaction_id =t .transaction_id )
        .count ()
        ==0
        )


def test_seed_batch_is_idempotent (db_session ):
    seed_batch (db_session )
    first =db_session .query (TransactionState ).count ()
    seed_batch (db_session )
    second =db_session .query (TransactionState ).count ()
    assert first ==second


def test_transactions_are_spread_over_time (db_session ):
    seed_batch (db_session )
    created =[t .created_at for t in db_session .query (TransactionState ).all ()]
    assert len (set (created ))>5
