"""Tests for the what-if simulator.

The properties that matter here are honesty properties: a simulated run must not
move the merchant's real numbers, the projection must not forecast recovery from
cases the engine is about to refuse, and the same scenario must realise the same
book twice so two runs can be compared.
"""

import asyncio
from datetime import datetime

import pytest

from application .constants import StoppingRule ,TransactionLifecycleState
from application .entities import TransactionState
from application .helpers import IST
from application .operations .compliance_rules import RBI_MAX_RETRIES ,VOICE_ATTEMPT_CAP
from application .operations .reconciliation_service import compute_metrics
from application .simulation import probability ,store ,triage
from application .simulation .scenario import (
SAMPLE_SCENARIOS ,
CaseShape ,
CustomCase ,
EdgeCases ,
PolicyOverrides ,
Scenario ,
plan ,
to_transaction ,
)


# ── The probability model ────────────────────────────────────────────────────


def _features (**kwargs ):
    base =dict (
    failure_class =2 ,
    playbook ="UPI_AUTOPAY_NUDGE",
    channel ="WHATSAPP",
    amount_inr =5000.0 ,
    )
    base .update (kwargs )
    return probability .CaseFeatures (**base )


def test_estimate_returns_the_prior_when_nothing_is_adverse ():
    result =probability .estimate (_features ())
    assert result .p ==pytest .approx (result .base_rate )
    assert result .contributions ==[]


def test_adverse_features_lower_the_estimate_and_are_explained ():
    result =probability .estimate (_features (in_quiet_hours =True ,retries_used =2 ))

    assert result .p <result .base_rate
    features ={c .feature for c in result .contributions }
    assert {"quiet_hours","retries_used"}<=features
    assert all (c .delta_pp <0 for c in result .contributions )
    # Sorted by magnitude so a UI can show the top driver first.
    magnitudes =[abs (c .delta_pp )for c in result .contributions ]
    assert magnitudes ==sorted (magnitudes ,reverse =True )


def test_a_blocked_case_projects_zero_not_merely_less ():
    """A bound is a wall, not a headwind.

    Without this the projection forecasts money from cases the engine is about
    to stop itself on, which is exactly the false claim the screen must not make.
    """
    result =probability .estimate (_features (blocked_by ="RBI retry cap"))

    assert result .p ==0.0
    assert result .variance ==0.0
    assert result .contributions [0 ].feature =="blocked"


def test_the_band_tightens_as_the_book_grows ():
    def relative_width (n ):
        cases =[(probability .estimate (_features (amount_inr =5000 )),5000.0 )]*n
        projection =probability .project (cases )
        return (projection .high_inr -projection .low_inr )/projection .expected_inr

    assert relative_width (400 )<relative_width (25 )


def test_observations_move_the_prior ():
    key =(1 ,"REROUTE_RAIL","PAYMENT_LINK")
    prior =probability .prior_for (*key )
    posterior =probability .observed_posteriors ([(*key ,False )]*40 )[key ]

    assert posterior .mean <prior .mean
    assert posterior .variance <prior .variance


def test_projection_of_an_empty_book_is_zero ():
    assert probability .project ([]).expected_inr ==0.0


# ── Routing triage ───────────────────────────────────────────────────────────


def _only_case (scenario :Scenario )->object :
    return plan (scenario ,"run")[0 ]


def test_a_clean_class1_case_stays_on_the_deterministic_path ():
    """A rail timeout, routine amount, no reply to read - no model call warranted."""
    case =_only_case (Scenario (
    cases =CaseShape (count =1 ,class_mix ={1 :1 },amount_scale =0.01 ),
    edge_cases =EdgeCases (reply_mix ={"silent":1.0 }),
    ))
    assert triage .assess (case ).needs_model is False


def test_a_free_text_reply_the_screen_cannot_classify_needs_the_model ():
    case =_only_case (Scenario (
    cases =CaseShape (count =0 ),
    custom_cases =[CustomCase (customer_name ="Asha",amount_inr =900 ,failure_class =1 ,
    reply_text ="paise 5 tarikh ko aayenge, thoda adjust karlo")],
    ))
    need =triage .assess (case )
    assert need .needs_model is True
    assert triage .REASON_FREE_TEXT in need .reasons


def test_a_clean_opt_out_is_handled_without_the_model ():
    """The deterministic screen catches it, so no advisory call is warranted."""
    case =_only_case (Scenario (
    cases =CaseShape (count =0 ),
    custom_cases =[CustomCase (customer_name ="Asha",amount_inr =900 ,failure_class =1 ,
    reply_text ="band karo")],
    ))
    assert triage .assess (case ).needs_model is False


def test_an_invoice_with_no_telemetry_and_high_value_needs_the_model ():
    case =_only_case (Scenario (cases =CaseShape (count =1 ,class_mix ={4 :1 })))
    need =triage .assess (case )
    assert need .needs_model is True
    assert triage .REASON_NO_TELEMETRY in need .reasons
    assert triage .REASON_STAKES in need .reasons


def test_the_last_available_retry_raises_the_case_to_the_model ():
    case =_only_case (Scenario (
    cases =CaseShape (count =1 ,class_mix ={1 :1 },amount_scale =0.01 ),
    edge_cases =EdgeCases (reply_mix ={"silent":1.0 },retries_already_used =RBI_MAX_RETRIES -1 ),
    ))
    need =triage .assess (case )
    assert need .needs_model is True
    assert triage .REASON_GUARDRAIL in need .reasons


def test_disposition_maps_each_final_state_to_one_lane ():
    assert triage .disposition (TransactionLifecycleState .ESCALATED .value )==triage .LANE_HUMAN
    assert triage .disposition (TransactionLifecycleState .WAITING .value )==triage .LANE_POSTPONED
    assert triage .disposition (TransactionLifecycleState .RECOVERED .value )==triage .LANE_CLOSED
    assert triage .disposition (TransactionLifecycleState .CANCELLED .value )==triage .LANE_CLOSED
    assert triage .disposition (TransactionLifecycleState .INTERVENING .value )==triage .LANE_IN_FLIGHT


def test_summarise_partitions_the_lanes_and_keeps_llm_outside_the_sum ():
    entries =[
    (True ,[triage .REASON_STAKES ],triage .LANE_HUMAN ),
    (True ,[triage .REASON_STAKES ,triage .REASON_NO_TELEMETRY ],triage .LANE_CLOSED ),
    (False ,[],triage .LANE_CLOSED ),
    (False ,[],triage .LANE_POSTPONED ),
    ]
    summary =triage .summarise (entries ,live_diagnosis =False )

    assert summary ["closed"]+summary ["human"]+summary ["postponed"]+summary ["in_flight"]==summary ["total"]==4
    assert summary ["llm"]==2
    assert summary ["deterministic_only"]==2
    assert summary ["model_calls_saved"]==2 and summary ["model_calls_made"]==0
    assert summary ["llm_reasons"][triage .REASON_STAKES ]==2


# ── Scenario planning ────────────────────────────────────────────────────────


def test_class_mix_is_apportioned_exactly ():
    cases =plan (Scenario (cases =CaseShape (count =100 ,class_mix ={1 :3 ,3 :1 })),"run")
    counts ={}
    for case in cases :
        counts [case .failure_class ]=counts .get (case .failure_class ,0 )+1

    assert counts =={1 :75 ,3 :25 }


def test_the_same_scenario_realises_the_same_book ():
    """Two runs must be comparable, so the draw is seeded from the scenario."""
    first =plan (SAMPLE_SCENARIOS ["tight_policy"],"run_a")
    second =plan (SAMPLE_SCENARIOS ["tight_policy"],"run_b")

    assert [c .outcome_event for c in first ]==[c .outcome_event for c in second ]
    assert [c .amount_minor for c in first ]==[c .amount_minor for c in second ]


def test_a_cooperative_reply_does_not_guarantee_settlement ():
    """Otherwise the recovered figure is asserted by the scenario, not produced."""
    scenario =Scenario (
    cases =CaseShape (count =120 ,class_mix ={2 :1 }),
    edge_cases =EdgeCases (reply_mix ={"cooperative":1.0 }),
    )
    outcomes =[case .outcome_event for case in plan (scenario ,"run")]

    assert any (o =="payment.captured"for o in outcomes )
    assert any (o is None for o in outcomes )


def test_settlement_quirk_percentages_land_exactly ():
    scenario =Scenario (
    cases =CaseShape (count =200 ),
    edge_cases =EdgeCases (late_settlement_pct =10 ,cross_device_pct =5 ),
    )
    cases =plan (scenario ,"run")

    assert sum (1 for c in cases if c .outcome_event =="payment.authorized")==20


def test_authored_outcomes_are_not_rewritten_by_generated_settlement_quirks ():
    scenario =Scenario (
    cases =CaseShape (count =10 ,class_mix ={1 :1 }),
    custom_cases =[CustomCase (customer_name ="Asha",amount_inr =1000,failure_class =1,outcome_event ="payment.captured")],
    edge_cases =EdgeCases (reply_mix ={"silent":1.0 },late_settlement_pct =20 ,cross_device_pct =20 ),
    )
    cases =plan (scenario ,"run")
    generated =cases [1:]

    assert cases [0].outcome_event =="payment.captured"
    assert [case .outcome_event for case in generated [:2]] ==["payment.authorized"]*2
    assert [case .outcome_event for case in generated [2:4]] ==["payment.captured"]*2
    assert sum (1 for case in generated if case .outcome_event =="payment.authorized")==2


def test_authored_class_four_inherits_the_scenario_overdue_default ():
    scenario =Scenario (
    cases =CaseShape (count =0 ),
    custom_cases =[CustomCase (customer_name ="Asha",amount_inr =1000,failure_class =4)],
    edge_cases =EdgeCases (days_overdue =48 ),
    )

    assert plan (scenario ,"run")[0].days_overdue ==48


def test_an_exhausted_retry_budget_zeroes_the_class3_projection ():
    scenario =Scenario (
    cases =CaseShape (count =20 ,class_mix ={3 :1 }),
    edge_cases =EdgeCases (retries_already_used =RBI_MAX_RETRIES ),
    )

    assert all (case .probability .p ==0.0 for case in plan (scenario ,"run"))


def test_scenario_rejects_an_empty_class_mix ():
    with pytest .raises (ValueError ):
        CaseShape (count =10 ,class_mix ={1 :0 })


def test_scenario_rejects_impossible_settlement_percentages ():
    with pytest .raises (ValueError ):
        EdgeCases (late_settlement_pct =70 ,cross_device_pct =70 )


def test_policy_overrides_layer_onto_the_live_policy ():
    base ={"max_discount_pct":15 ,"allowed_channels":["WHATSAPP","VOICE"]}
    merged =PolicyOverrides (max_discount_pct =0 ).applied_to (base )

    assert merged =={"max_discount_pct":0 ,"allowed_channels":["WHATSAPP","VOICE"]}
    assert base ["max_discount_pct"]==15


# ── Isolation from the real book ─────────────────────────────────────────────


def test_simulated_rows_are_excluded_from_the_real_metrics (db_session ):
    real =to_transaction (plan (Scenario (cases =CaseShape (count =1 )),"keep")[0 ],"keep")
    real .metadata_json .pop ("simulation_run_id")
    real .current_state =TransactionLifecycleState .RECOVERED
    db_session .add (real )

    simulated =to_transaction (plan (Scenario (cases =CaseShape (count =1 )),"sim_run")[0 ],"sim_run")
    simulated .current_state =TransactionLifecycleState .RECOVERED
    db_session .add (simulated )
    db_session .commit ()

    assert compute_metrics (db_session )["counts"]["total"]==1
    assert compute_metrics (db_session ,simulation_run_id ="sim_run")["counts"]["total"]==1
    assert compute_metrics (db_session ,simulation_run_id ="nope")["counts"]["total"]==0


def test_the_case_list_hides_simulated_rows_unless_asked (client ,db_session ):
    simulated =to_transaction (plan (Scenario (cases =CaseShape (count =1 )),"sim_run")[0 ],"sim_run")
    db_session .add (simulated )
    db_session .commit ()

    assert client .get ("/api/v1/transactions").json ()["total"]==0

    scoped =client .get ("/api/v1/transactions",params ={"simulation_run_id":"sim_run"}).json ()
    assert scoped ["total"]==1


def test_deleting_a_run_removes_its_rows (db_session ):
    for case in plan (Scenario (cases =CaseShape (count =3 )),"doomed"):
        db_session .add (to_transaction (case ,"doomed"))
    db_session .commit ()

    assert store .delete_run (db_session ,"doomed")==3
    assert db_session .query (TransactionState ).count ()==0
    assert store .delete_run (db_session ,"doomed")==0


def test_prune_keeps_only_the_newest_runs (db_session ):
    for run_id in ("run_a","run_b","run_c"):
        db_session .add (to_transaction (plan (Scenario (cases =CaseShape (count =1 )),run_id )[0 ],run_id ))
        db_session .commit ()

    store .prune (db_session ,keep =1 )

    assert len (store .list_runs (db_session ))==1


# ── The endpoints ────────────────────────────────────────────────────────────


def test_sample_scenarios_are_offered_for_the_one_click_path (client ):
    payload =client .get ("/api/v1/simulate/scenarios").json ()
    keys ={item ["key"]for item in payload ["presets"]}

    assert keys ==set (SAMPLE_SCENARIOS )
    assert all (item ["description"]for item in payload ["presets"])


def test_unknown_run_is_a_404 (client ):
    assert client .get ("/api/v1/simulate/runs/nope").status_code ==404
    assert client .delete ("/api/v1/simulate/runs/nope").status_code ==404


def test_batch_rejects_an_out_of_range_concurrency (client ):
    body ={"scenario":Scenario (cases =CaseShape (count =1 )).model_dump (mode ="json"),"concurrency":999 }

    assert client .post ("/api/v1/simulate/batch",json =body ).status_code ==422


# ── A whole run ──────────────────────────────────────────────────────────────


def _drain (scenario ,concurrency =4 ):
    async def go ():
        events =[]
        from application .simulation .runner import run

        async for name ,data in run (scenario ,concurrency =concurrency ):
            events .append ((name ,data ))
        return events

    return asyncio .run (go ())


@pytest .fixture ()
def sim_db (monkeypatch ,tmp_path ):
    """A throwaway database the worker pool can open its own sessions against.

    A file rather than ``sqlite://`` on purpose: the pool opens one Session per
    worker thread, which an in-memory database cannot serve, and a file also
    exercises the WAL configuration the concurrency actually depends on.
    """
    from sqlalchemy import create_engine
    from sqlalchemy .orm import sessionmaker

    import application .simulation .runner as runner_mod
    from application .persistence import Base

    engine =create_engine (
    f"sqlite:///{tmp_path /'sim.db'}",connect_args ={"check_same_thread":False }
    )
    with engine .connect ()as connection :
        connection .exec_driver_sql ("PRAGMA journal_mode=WAL")
        connection .exec_driver_sql ("PRAGMA busy_timeout=5000")
    Base .metadata .create_all (bind =engine )

    factory =sessionmaker (autocommit =False ,autoflush =False ,bind =engine )
    monkeypatch .setattr (runner_mod ,"SessionLocal",factory )

    session =factory ()
    try :
        yield session
    finally :
        session .close ()
        engine .dispose ()


def test_a_run_streams_start_cases_and_a_complete (sim_db ):
    scenario =Scenario (
    name ="tiny",
    cases =CaseShape (count =6 ,class_mix ={1 :1 }),
    edge_cases =EdgeCases (clock_ist =datetime (2026 ,3 ,4 ,11 ,0 ,tzinfo =IST )),
    )
    events =_drain (scenario ,concurrency =1 )
    names =[name for name ,_ in events ]

    assert names [0 ]=="start"
    assert names [-1 ]=="complete"
    assert sum (1 for n in names if n =="case")==6

    complete =events [-1 ][1 ]
    assert complete ["counts"]["total"]==6
    assert complete ["throughput"]["cases_per_sec"]>0
    # Measured and modelled are reported as two separate figures on purpose.
    assert "recovered_inr"in complete and "projected_inr"in complete
    assert len (complete ["projected_band"])==2

    # The routing split: outcome lanes partition the book, LLM sits alongside.
    routing =complete ["routing"]
    assert routing ["closed"]+routing ["human"]+routing ["postponed"]+routing ["in_flight"]==6
    assert routing ["llm"]+routing ["deterministic_only"]==6
    per_case =[data for name ,data in events if name =="case"]
    assert all ("triage_lane"in c and "needs_model"in c for c in per_case )


def test_quiet_hours_defer_the_whole_book_and_are_named (sim_db ):
    scenario =Scenario (
    name ="night",
    cases =CaseShape (count =4 ,class_mix ={2 :1 }),
    edge_cases =EdgeCases (
    reply_mix ={"cooperative":1.0 },
    clock_ist =datetime (2026 ,3 ,4 ,21 ,40 ,tzinfo =IST ),
    ),
    )
    events =_drain (scenario ,concurrency =2 )
    cases =[data for name ,data in events if name =="case"]
    complete =events [-1 ][1 ]

    assert all (c ["final_state"]==TransactionLifecycleState .WAITING .value for c in cases )
    assert all (c ["stopped_by"]==StoppingRule .TRAI_QUIET_HOURS .value for c in cases )
    assert complete ["deferred_inr"]>0
    assert complete ["recovered_inr"]==0


def test_an_opt_out_stops_the_case_and_names_the_rule (sim_db ):
    scenario =Scenario (
    name ="traced",
    cases =CaseShape (count =2 ,class_mix ={2 :1 }),
    edge_cases =EdgeCases (
    reply_mix ={"opt_out":1.0 },
    clock_ist =datetime (2026 ,3 ,4 ,11 ,0 ,tzinfo =IST ),
    ),
    )
    cases =[data for name ,data in _drain (scenario ,concurrency =1 )if name =="case"]

    assert all (c ["stopped_by"]==StoppingRule .OPT_OUT .value for c in cases )
    assert all (c ["final_state"]==TransactionLifecycleState .CANCELLED .value for c in cases )


def test_a_tight_policy_escalates_instead_of_dispatching (sim_db ):
    """The sandbox's own wording is what reaches the screen."""
    scenario =Scenario (
    name ="locked down",
    cases =CaseShape (count =3 ,class_mix ={1 :1 }),
    edge_cases =EdgeCases (
    reply_mix ={"cooperative":1.0 },
    clock_ist =datetime (2026 ,3 ,4 ,11 ,0 ,tzinfo =IST ),
    ),
    policy =PolicyOverrides (allowed_actions =["SEND_WHATSAPP"]),
    )
    events =_drain (scenario ,concurrency =1 )
    cases =[data for name ,data in events if name =="case"]

    assert all (c ["final_state"]==TransactionLifecycleState .ESCALATED .value for c in cases )


def test_a_run_does_not_touch_the_merchant_policy (sim_db ):
    from application .operations .policy_repository import get_policy

    before =get_policy (sim_db )
    _drain (
    Scenario (
    name ="override",
    cases =CaseShape (count =2 ,class_mix ={1 :1 }),
    edge_cases =EdgeCases (clock_ist =datetime (2026 ,3 ,4 ,11 ,0 ,tzinfo =IST )),
    policy =PolicyOverrides (max_discount_pct =0 ,allowed_actions =["SEND_WHATSAPP"]),
    ),
    concurrency =1 ,
    )

    assert get_policy (sim_db )==before


def test_concurrency_is_bounded_by_the_request (sim_db ):
    scenario =Scenario (
    name ="pool",
    cases =CaseShape (count =12 ,class_mix ={1 :1 }),
    edge_cases =EdgeCases (clock_ist =datetime (2026 ,3 ,4 ,11 ,0 ,tzinfo =IST )),
    )
    events =_drain (scenario ,concurrency =3 )
    complete =events [-1 ][1 ]

    assert complete ["counts"]["total"]==12
    assert complete ["throughput"]["peak_workers"]<=3


# ── Part A: authored cases and saved scenarios ───────────────────────────────

def test_authored_free_text_is_screened_by_the_real_compliance_rule (sim_db ):
    scenario =Scenario (
    cases =CaseShape (count =0 ),
    custom_cases =[CustomCase (customer_name ="Asha",amount_inr =1250.50,failure_class =2,reply_text ="band karo")],
    edge_cases =EdgeCases (clock_ist =datetime (2026 ,3 ,4 ,11 ,0 ,tzinfo =IST )),
    )
    cases =[data for name ,data in _drain (scenario ,concurrency =1 )if name =="case"]

    assert cases [0]["final_state"]==TransactionLifecycleState .CANCELLED .value
    assert cases [0]["stopped_by"]==StoppingRule .OPT_OUT .value


def test_authored_and_generated_cases_are_deterministic (sim_db ):
    scenario =Scenario (
    name ="mixed authored",
    cases =CaseShape (count =3 ,class_mix ={1 :1 }),
    custom_cases =[CustomCase (customer_name ="Asha",amount_inr =1250.50,failure_class =2,reply_text ="hello")],
    )
    first =plan (scenario ,"run_a")
    second =plan (scenario ,"run_b")

    assert len (first)==4
    assert [c .customer_name for c in first ]==["Asha","Meera Iyer","Rohan Das","Kavya Bhat"]
    assert [(c .amount_minor ,c .failure_class ,c .user_message )for c in first ]==[(c .amount_minor ,c .failure_class ,c .user_message )for c in second ]


def test_explicit_generated_amount_bounds_are_honoured (sim_db ):
    scenario =Scenario (cases =CaseShape (count =30 ,class_mix ={1 :1 ,4 :1 },amount_min_inr =1000 ,amount_max_inr =2000 ))
    assert all (1000 <=case .amount_inr <=2000 for case in plan (scenario ,"run"))


def test_live_diagnosis_is_capped_to_a_small_book ():
    with pytest .raises (ValueError ,match ="25"):
        Scenario (cases =CaseShape (count =26 ),live_diagnosis =True )


def test_saved_scenario_round_trips_through_api (client ):
    scenario =Scenario (
    name ="Saved Hinglish opt out",
    cases =CaseShape (count =0 ),
    custom_cases =[CustomCase (customer_name ="Asha",amount_inr =999,failure_class =1,reply_text ="band karo")],
    )
    body ={
    "slug":"saved-hinglish-opt-out",
    "name":scenario .name ,
    "description":"A small custom book",
    "payload":scenario .model_dump (mode ="json"),
    }
    created =client .post ("/api/v1/simulate/scenarios",json =body )
    assert created .status_code ==200
    assert created .json ()["payload"]==body ["payload"]

    catalog =client .get ("/api/v1/simulate/scenarios").json ()
    assert [saved ["slug"]for saved in catalog ["saved"]]==[body ["slug"]]

    deleted =client .delete ("/api/v1/simulate/scenarios/saved-hinglish-opt-out")
    assert deleted .status_code ==200
    assert client .get ("/api/v1/simulate/scenarios").json ()["saved"]==[]
