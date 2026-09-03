"""Enriched metrics that back the dashboard overview: funnel, channel mix,
recovery-over-time, stopping-rule breakdown, and per-class depth. Computed from
the batch-seeded durable tables so the numbers are earned."""

from application .constants import FailureClass ,TransactionLifecycleState
from application .entities import TransactionState
from application .operations .batch_seed import seed_batch
from application .operations .reconciliation_service import compute_metrics


def test_grrr_excludes_healthy_rows (db_session ):
    seed_batch (db_session )
    m =compute_metrics (db_session )

    at_risk_rows =[
    t
    for t in db_session .query (TransactionState ).all ()
    if (t .metadata_json or {}).get ("is_at_risk")
    ]
    at_risk_inr =round (sum (t .amount_minor for t in at_risk_rows )/100 ,2 )
    assert m ["at_risk_inr"]==at_risk_inr
    assert 0.0 <m ["grrr"]<=1.0


def test_metrics_expose_a_recovery_funnel (db_session ):
    seed_batch (db_session )
    m =compute_metrics (db_session )
    funnel =m ["funnel"]
    for key in ("at_risk","intervened","recovered","escalated","cancelled"):
        assert key in funnel
    assert funnel ["at_risk"]>=funnel ["recovered"]>=0


def test_metrics_expose_channel_breakdown (db_session ):
    seed_batch (db_session )
    m =compute_metrics (db_session )
    channels =m ["channel_breakdown"]
    assert channels
    total_dispatched =sum (c ["dispatched"]for c in channels .values ())
    assert total_dispatched >=1


def test_metrics_expose_recovery_time_series (db_session ):
    seed_batch (db_session )
    m =compute_metrics (db_session )
    ts =m ["time_series"]
    assert len (ts )>=1

    cumulative =[point ["cumulative_inr"]for point in ts ]
    assert cumulative ==sorted (cumulative )
    assert cumulative [-1 ]==m ["recovered_inr"]


def test_metrics_break_down_stopping_rules_by_name (db_session ):
    seed_batch (db_session )
    m =compute_metrics (db_session )
    rules =m ["stopping_rules_by_name"]

    assert sum (rules .values ())>=1


def test_by_class_is_enriched (db_session ):
    seed_batch (db_session )
    m =compute_metrics (db_session )
    for fc in FailureClass :
        cls =m ["by_class"][str (int (fc ))]
        assert "recovery_rate"in cls
        assert "top_playbook"in cls
        assert 0.0 <=cls ["recovery_rate"]<=1.0


def test_class_specific_stopping_rules_now_fire (db_session ):
    seed_batch (db_session )
    m =compute_metrics (db_session )
    rules =m ["stopping_rules_by_name"]

    assert rules .get ("NO_DOUBLE_CHARGE",0 )>=1
    assert rules .get ("CROSS_DEVICE_COMPLETION",0 )>=1
