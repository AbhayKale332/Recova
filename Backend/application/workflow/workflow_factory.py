"""Production dependency wiring for diagnosis, policy validation, persistence, and dispatch."""

from fastapi import Depends
from sqlalchemy .orm import Session

from application .integrations .routing_dispatcher import build_dispatcher
from application .persistence import get_db
from application .workflow .recovery_graph import OrchestratorDeps
from application .operations .policy_repository import sandbox_for


def get_orchestrator_deps (db :Session =Depends (get_db ))->OrchestratorDeps :


    from application .operations .ai_client import default_diagnosis_engine

    return OrchestratorDeps (
    db =db ,
    diagnosis =default_diagnosis_engine (),

    sandbox =sandbox_for (db ),
    dispatch =build_dispatcher (db ),
    )
