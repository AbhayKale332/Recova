"""Concurrent execution of a scenario against the real recovery engine.

Every case here runs the same LangGraph the webhook path runs, with the same
PolicySandbox and the same compliance rules. Nothing about the decisions is
simulated - what is simulated is the *book*: which failures exist, what the
customers say, and what time it is. That distinction is the whole point, because
a reason shown on screen is only worth anything if it came from the code that
would run in production.

Concurrency notes, since this is also the scalability story:

* A SQLAlchemy Session is not thread-safe, and every graph node commits. Each
  case therefore gets its own Session, opened and closed inside the worker.
* The graph is synchronous, so it runs in a worker thread via ``to_thread`` and
  the semaphore bounds how many of those exist at once.
* SQLite needs WAL for this to work at all - see ``persistence._configure_sqlite``.
* The queue is in-process. It is real concurrency, not a distributed system;
  do not describe it as one.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import asdict ,dataclass ,field
from datetime import datetime
from typing import AsyncIterator ,Callable

from application .constants import TransactionLifecycleState
from application .entities import AuditTrail ,TransactionState
from application .operations .batch_seed import offline_diagnosis_engine
from application .operations .ai_client import default_diagnosis_engine
from application .operations .policy_guard import PolicySandbox
from application .operations .policy_repository import get_policy
from application .operations .reconciliation_service import compute_metrics
from application .persistence import SessionLocal
from application .simulation import probability ,scenario as scenario_mod ,trace ,triage
from application .simulation .scenario import PlannedCase ,Scenario
from application .workflow .recovery_graph import OrchestratorDeps ,build_recovery_graph

DEFAULT_CONCURRENCY =8
MAX_CONCURRENCY =32

# Progress is coalesced rather than emitted per case: at 200 cases and 8 workers
# a per-case event would flood the stream and tell the reader nothing extra.
_PROGRESS_INTERVAL_SEC =0.1

Event =tuple [str ,dict ]


@dataclass
class CaseResult :
    transaction_id :str
    failure_class :int
    amount_inr :float
    customer_name :str
    final_state :str
    stopped_by :str |None
    probability :float
    base_rate :float =0.0
    contributions :list [dict ]=field (default_factory =list )
    elapsed_ms :float =0.0
    trace :list [dict ]=field (default_factory =list )
    # Routing triage: whether production would spend an advisory model call on
    # this case, and which lane the finished case lands in. See simulation.triage.
    needs_model :bool =False
    triage_reasons :list [str ]=field (default_factory =list )
    triage_lane :str =triage .LANE_CLOSED


def _percentile (sorted_values :list [float ],fraction :float )->float :
    """Nearest-rank percentile. No numpy in this project, and none needed."""
    if not sorted_values :
        return 0.0
    rank =max (1 ,min (len (sorted_values ),round (fraction *len (sorted_values ))))
    return round (sorted_values [rank -1 ],2 )


def _run_one (case :PlannedCase ,policy :dict ,run_id :str ,clock :datetime ,live_diagnosis :bool =False )->CaseResult :
    """Execute one case end to end. Runs in a worker thread with its own Session."""
    started =time .perf_counter ()
    db =SessionLocal ()
    try :
        db .add (scenario_mod .to_transaction (case ,run_id ))
        db .commit ()

        deps =OrchestratorDeps (
        db =db ,
        # Offline diagnosis: N live model calls would dominate the latency this
        # screen is measuring, and would hit rate limits mid-demo. The routing
        # it produces is the same deterministic per-class default the live
        # engine falls back to.
        diagnosis =default_diagnosis_engine ()if live_diagnosis else offline_diagnosis_engine (),
        sandbox =PolicySandbox (policy ),
        dispatch =_recording_dispatch (),
        clock =lambda :clock ,
        )
        build_recovery_graph (deps ).invoke (scenario_mod .initial_state (case ,clock ))

        txn =(
        db .query (TransactionState )
        .filter_by (transaction_id =case .transaction_id )
        .one ()
        )
        rows =(
        db .query (AuditTrail )
        .filter_by (transaction_id =case .transaction_id )
        .order_by (AuditTrail .id )
        .all ()
        )
        steps =trace .build (rows )
        stopped_by =next (
        (step .rule for step in reversed (steps )if step .rule ),None
        )

        final_state =txn .current_state .value
        need =triage .assess (case )

        return CaseResult (
        transaction_id =case .transaction_id ,
        failure_class =case .failure_class ,
        amount_inr =case .amount_inr ,
        customer_name =case .customer_name ,
        final_state =final_state ,
        stopped_by =stopped_by ,
        probability =case .probability .p ,
        base_rate =case .probability .base_rate ,
        contributions =[asdict (c )for c in case .probability .contributions ],
        elapsed_ms =round ((time .perf_counter ()-started )*1000 ,2 ),
        trace =trace .serialize (steps ),
        needs_model =need .needs_model ,
        triage_reasons =need .reasons ,
        triage_lane =triage .disposition (final_state ),
        )
    finally :
        db .close ()


def _recording_dispatch ()->Callable :
    """Channel dispatch for a simulated run.

    The real dispatcher already simulates every channel unless ``LIVE_MODE`` is
    on. This is a narrower promise: a what-if never reaches a customer, whatever
    the environment is configured to do.
    """

    def dispatch (action ,state ):
        return {"delivered":True ,"simulated":True }

    return dispatch


async def run (sc :Scenario ,concurrency :int =DEFAULT_CONCURRENCY )->AsyncIterator [Event ]:
    """Drive a whole scenario, yielding SSE events as it goes."""
    concurrency =max (1 ,min (concurrency ,MAX_CONCURRENCY ))
    run_id =uuid .uuid4 ().hex
    clock =sc .edge_cases .clock ()
    cases =scenario_mod .plan (sc ,run_id )

    # The scenario's policy exists only for this run: the merchant's live policy
    # with the overrides layered on top, never written back. A what-if must not
    # silently change what the engine is allowed to do tomorrow.
    setup =SessionLocal ()
    try :
        policy =sc .policy .applied_to (get_policy (setup ))
    finally :
        setup .close ()

    projection =probability .project (
    [(case .probability ,case .amount_inr )for case in cases ]
    )

    yield "start",{
    "run_id":run_id ,
    "total":len (cases ),
    "at_risk_inr":round (sum (case .amount_inr for case in cases ),2 ),
    "concurrency":concurrency ,
    "clock_ist":clock .isoformat (),
    "scenario":sc .name ,
    "projected_inr":projection .expected_inr ,
    "projected_band":[projection .low_inr ,projection .high_inr ],
    }

    semaphore =asyncio .Semaphore (concurrency )
    busy =0
    peak_busy =0
    durations :list [float ]=[]
    results :list [CaseResult ]=[]
    started =time .perf_counter ()

    async def worker (case :PlannedCase )->CaseResult :
        nonlocal busy ,peak_busy
        async with semaphore :
            busy +=1
            peak_busy =max (peak_busy ,busy )
            try :
                return await asyncio .to_thread (_run_one ,case ,policy ,run_id ,clock ,sc .live_diagnosis )
            finally :
                busy -=1

    pending =[asyncio .create_task (worker (case ))for case in cases ]
    last_progress =0.0

    for finished in asyncio .as_completed (pending ):
        result =await finished
        results .append (result )
        durations .append (result .elapsed_ms )

        yield "case",{
        "transaction_id":result .transaction_id ,
        "failure_class":result .failure_class ,
        "amount_inr":result .amount_inr ,
        "customer_name":result .customer_name ,
        "final_state":result .final_state ,
        "stopped_by":result .stopped_by ,
        "p":round (result .probability ,4 ),
        "base_rate":round (result .base_rate ,4 ),
        "contributions":result .contributions ,
        "elapsed_ms":result .elapsed_ms ,
        "needs_model":result .needs_model ,
        "triage_lane":result .triage_lane ,
        "triage_reasons":result .triage_reasons ,
        }

        now =time .perf_counter ()
        is_last =len (results )==len (cases )
        if is_last or now -last_progress >=_PROGRESS_INTERVAL_SEC :
            last_progress =now
            elapsed =max (now -started ,1e-6 )
            ordered =sorted (durations )
            yield "progress",{
            "done":len (results ),
            "total":len (cases ),
            "rate":round (len (results )/elapsed ,2 ),
            "p50_ms":_percentile (ordered ,0.50 ),
            "p95_ms":_percentile (ordered ,0.95 ),
            "workers_busy":busy ,
            "peak_workers":peak_busy ,
            "elapsed_s":round (elapsed ,3 ),
            }

    elapsed =max (time .perf_counter ()-started ,1e-6 )
    yield "complete",_summary (run_id ,sc ,results ,projection ,elapsed ,concurrency ,peak_busy )


def _summary (
run_id :str ,
sc :Scenario ,
results :list [CaseResult ],
projection :probability .Projection ,
elapsed :float ,
concurrency :int ,
peak_busy :int ,
)->dict :
    db =SessionLocal ()
    try :
        metrics =compute_metrics (db ,simulation_run_id =run_id )
    finally :
        db .close ()

    stopped =[r for r in results if r .stopped_by ]
    ordered =sorted (r .elapsed_ms for r in results )

    # Deferred money is neither recovered nor lost, and the gap between the
    # measured and projected figures is mostly this. Reporting it stops the two
    # numbers looking like a contradiction: the projection expects these cases to
    # settle, the run just has not reached the hour when it may contact them.
    deferred_inr =round (
    sum (
    r .amount_inr
    for r in results
    if r .final_state ==TransactionLifecycleState .WAITING .value
    ),
    2 ,
    )

    return {
    "run_id":run_id ,
    "scenario":sc .name ,
    # Measured: what the engine actually drove to RECOVERED.
    "recovered_inr":metrics ["recovered_inr"],
    "at_risk_inr":metrics ["at_risk_inr"],
    "grrr":metrics ["grrr"],
    # Modelled: expected value across the book, with a 95% band. Never present
    # this as money that moved.
    "projected_inr":projection .expected_inr ,
    "projected_band":[projection .low_inr ,projection .high_inr ],
    "projected_cases":projection .expected_cases ,
    "deferred_inr":deferred_inr ,
    "counts":{
    "total":len (results ),
    "recovered":sum (1 for r in results if r .final_state ==TransactionLifecycleState .RECOVERED .value ),
    "escalated":sum (1 for r in results if r .final_state ==TransactionLifecycleState .ESCALATED .value ),
    "stopped":sum (1 for r in results if r .final_state ==TransactionLifecycleState .CANCELLED .value ),
    "waiting":sum (1 for r in results if r .final_state ==TransactionLifecycleState .WAITING .value ),
    "rules_fired":len (stopped ),
    },
    # How the book splits by who made the call: deterministic code, the advisory
    # model, or a human - plus what was deferred. The batch keeps diagnosis
    # offline, so this is the split production *would* see, measured per case.
    "routing":triage .summarise (
    ((r .needs_model ,r .triage_reasons ,r .triage_lane )for r in results ),
    live_diagnosis =sc .live_diagnosis ,
    ),
    "stopping_rules_by_name":metrics ["stopping_rules_by_name"],
    "by_class":metrics ["by_class"],
    "funnel":metrics ["funnel"],
    "throughput":{
    "elapsed_s":round (elapsed ,3 ),
    "cases_per_sec":round (len (results )/elapsed ,2 ),
    "p50_ms":_percentile (ordered ,0.50 ),
    "p95_ms":_percentile (ordered ,0.95 ),
    "concurrency":concurrency ,
    "peak_workers":peak_busy ,
    },
    "metrics":metrics ,
    }
