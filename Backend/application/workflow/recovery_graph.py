"""LangGraph definition for the durable ingest, diagnosis, intervention, and reconciliation flow."""

from dataclasses import dataclass ,field
from datetime import datetime
from typing import Callable

from langgraph .graph import END ,START ,StateGraph
from sqlalchemy .orm import Session

from application .helpers import now_ist
from application .workflow import workflow_nodes as node_defs
from application .workflow .workflow_state import RecoveryState
from application .operations .diagnosis_service import DiagnosisEngine
from application .operations .policy_guard import PolicySandbox


@dataclass
class OrchestratorDeps :
    """Everything the graph needs to reach the outside world.

    Injected rather than imported so the orchestrator is testable offline: tests
    pass a fake diagnosis engine and a recording dispatcher, while production
    wires the Gemini engine and the live/sim channel dispatcher.
    """

    db :Session
    diagnosis :DiagnosisEngine
    sandbox :PolicySandbox
    dispatch :Callable

    # The IST wall clock the compliance gates read. Injected like everything else
    # here so a test is not time-of-day dependent and a simulated scenario can ask
    # what the engine would do at 21:40. A per-case override may still arrive on
    # the state as ``now_ist``.
    clock :Callable [[],datetime ]=field (default =now_ist )


def build_recovery_graph (deps :OrchestratorDeps ,checkpointer =None ):
    # Nodes perform persistence and auditing; this builder defines only control-flow transitions.
    nodes =node_defs .build_nodes (deps )

    builder =StateGraph (RecoveryState )
    for name ,fn in nodes .items ():
        builder .add_node (name ,fn )

    # Early exits are represented by conditional edges so terminal states skip later actions.
    builder .add_edge (START ,"ingest")
    builder .add_conditional_edges (
    "ingest",node_defs .route_after_ingest ,{"diagnose":"diagnose",END :END }
    )
    builder .add_conditional_edges (
    "diagnose",node_defs .route_after_diagnose ,{"wait":"wait","execute":"execute"}
    )
    builder .add_edge ("wait","execute")
    builder .add_conditional_edges (
    "execute",node_defs .route_after_execute ,{"reconcile":"reconcile",END :END }
    )
    builder .add_edge ("reconcile",END )

    return builder .compile (checkpointer =checkpointer )
