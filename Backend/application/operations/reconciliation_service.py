"""Auditable financial metrics derived from transaction and audit records."""

from collections import defaultdict

from sqlalchemy .orm import Session

from application .constants import (
ActionType ,
FailureClass ,
TransactionLifecycleState ,
)
from application .entities import AuditTrail ,EscalationQueue ,TransactionState

_PAISE_PER_RUPEE =100


def _inr (paise :int |None )->float :
    return round ((paise or 0 )/_PAISE_PER_RUPEE ,2 )


def _is_at_risk (t :TransactionState )->bool :
    return bool ((t .metadata_json or {}).get ("is_at_risk",True ))


def _recovered (t :TransactionState )->bool :
    return t .current_state ==TransactionLifecycleState .RECOVERED


def compute_metrics (db :Session )->dict :
    transactions =db .query (TransactionState ).all ()
    audits =db .query (AuditTrail ).all ()
    at_risk =[t for t in transactions if _is_at_risk (t )]

    # Compute financial metrics from durable records so dashboard values remain auditable.
    at_risk_paise =sum (t .amount_minor for t in at_risk )
    recovered_paise =sum (t .amount_minor for t in at_risk if _recovered (t ))

    return {
    "at_risk_inr":_inr (at_risk_paise ),
    "recovered_inr":_inr (recovered_paise ),
    "in_flight_inr":_inr (
    sum (
    t .amount_minor
    for t in at_risk
    if t .current_state
    in (TransactionLifecycleState .INTERVENING ,TransactionLifecycleState .WAITING )
    )
    ),
    "lost_inr":_inr (
    sum (t .amount_minor for t in at_risk if t .current_state ==TransactionLifecycleState .FAILED )
    ),
    "grrr":round (recovered_paise /at_risk_paise ,4 )if at_risk_paise else 0.0 ,
    "by_class":_by_class (at_risk ,audits ),
    "funnel":_funnel (at_risk ,audits ),
    "channel_breakdown":_channel_breakdown (transactions ,audits ),
    "time_series":_time_series (at_risk ),
    "stopping_rules_by_name":_stopping_rules_by_name (audits ,db ),
    "counts":_counts (transactions ,db ,audits ),
    "avg_time_to_recovery_seconds":_avg_ttr (at_risk ),
    }


def _intervention_audits (audits :list [AuditTrail ])->list [AuditTrail ]:
    return [a for a in audits if a .action_type ==ActionType .INTERVENTION_DISPATCH ]


def _playbook_of (txn_id :str ,audits :list [AuditTrail ])->str |None :
    for a in _intervention_audits (audits ):
        if a .transaction_id ==txn_id and isinstance (a .payload ,dict ):
            return a .payload .get ("playbook")
    return None


def _by_class (at_risk :list [TransactionState ],audits :list [AuditTrail ])->dict :
    by_class :dict [str ,dict ]={}
    for fc in FailureClass :
        rows =[t for t in at_risk if int (t .failure_class )==int (fc )]
        recovered_rows =[t for t in rows if _recovered (t )]
        playbooks :dict [str ,int ]=defaultdict (int )
        for t in rows :
            pb =_playbook_of (t .transaction_id ,audits )
            if pb :
                playbooks [pb ]+=1
        top_playbook =max (playbooks ,key =playbooks .get )if playbooks else None
        by_class [str (int (fc ))]={
        "at_risk_inr":_inr (sum (t .amount_minor for t in rows )),
        "recovered_inr":_inr (sum (t .amount_minor for t in recovered_rows )),
        "count":len (rows ),
        "recovered_count":len (recovered_rows ),
        "recovery_rate":round (len (recovered_rows )/len (rows ),4 )if rows else 0.0 ,
        "top_playbook":top_playbook ,
        "avg_time_to_recovery_seconds":_avg_ttr (recovered_rows ),
        }
    return by_class


def _funnel (at_risk :list [TransactionState ],audits :list [AuditTrail ])->dict :
    intervened_ids ={a .transaction_id for a in _intervention_audits (audits )}

    def _n (state :TransactionLifecycleState )->int :
        return sum (1 for t in at_risk if t .current_state ==state )

    return {
    "at_risk":len (at_risk ),
    "intervened":sum (1 for t in at_risk if t .transaction_id in intervened_ids ),
    "recovered":_n (TransactionLifecycleState .RECOVERED ),
    "escalated":_n (TransactionLifecycleState .ESCALATED ),
    "cancelled":_n (TransactionLifecycleState .CANCELLED ),
    "failed":_n (TransactionLifecycleState .FAILED ),
    }


def _channel_breakdown (transactions :list [TransactionState ],audits :list [AuditTrail ])->dict :
    recovered_ids ={t .transaction_id for t in transactions if _recovered (t )}
    out :dict [str ,dict ]=defaultdict (lambda :{"dispatched":0 ,"recovered":0 })
    for a in _intervention_audits (audits ):
        if not isinstance (a .payload ,dict ):
            continue
        channel =a .payload .get ("channel")or "PAYMENT_LINK"
        out [channel ]["dispatched"]+=1
        if a .transaction_id in recovered_ids :
            out [channel ]["recovered"]+=1
    return dict (out )


def _time_series (at_risk :list [TransactionState ])->list [dict ]:
    """Cumulative recovered revenue per day (keyed off when recovery settled)."""
    per_day :dict [str ,int ]=defaultdict (int )
    for t in at_risk :
        if _recovered (t ):
            per_day [t .updated_at .date ().isoformat ()]+=t .amount_minor
    running =0
    series =[]
    for day in sorted (per_day ):
        running +=per_day [day ]
        series .append (
        {
        "date":day ,
        "recovered_inr":_inr (per_day [day ]),
        "cumulative_inr":_inr (running ),
        }
        )
    return series


def _stopping_rules_by_name (audits :list [AuditTrail ],db :Session )->dict :
    counts :dict [str ,int ]=defaultdict (int )
    for a in audits :
        if isinstance (a .payload ,dict )and a .payload .get ("stopping_rule"):
            counts [a .payload ["stopping_rule"]]+=1


    for e in db .query (EscalationQueue ).all ():
        if e .rule :
            counts [e .rule .value ]+=1
    return dict (counts )


def _counts (transactions :list [TransactionState ],db :Session ,audits :list [AuditTrail ])->dict :
    def _n (state :TransactionLifecycleState )->int :
        return sum (1 for t in transactions if t .current_state ==state )

    stopping =sum (
    1 for a in audits if isinstance (a .payload ,dict )and a .payload .get ("stopping_rule")
    )
    return {
    "total":len (transactions ),
    "interventions":len (_intervention_audits (audits )),
    "escalations":db .query (EscalationQueue ).count (),
    "stopping_rules_fired":stopping ,
    "recovered":_n (TransactionLifecycleState .RECOVERED ),
    "cancelled":_n (TransactionLifecycleState .CANCELLED ),
    "failed":_n (TransactionLifecycleState .FAILED ),
    }


def _avg_ttr (rows :list [TransactionState ])->float :
    recovered =[t for t in rows if _recovered (t )]
    if not recovered :
        return 0.0
    return round (
    sum ((t .updated_at -t .created_at ).total_seconds ()for t in recovered )/len (recovered ),
    2 ,
    )
