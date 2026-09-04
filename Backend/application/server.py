"""FastAPI application entry point and router registration for the payment recovery service."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi .middleware .cors import CORSMiddleware

from application .settings import settings
from application .persistence import init_db
from application .endpoints import (
admin_api ,
    assistant_api ,
    live_api ,
health_api ,
metrics_api ,
router_api ,
policy_api ,
simulation_api ,
stream_api ,
tracker_api ,
transaction_api ,
webhook_api ,
)


# Startup owns table initialization; schema evolution should still be handled by migrations.
@asynccontextmanager
async def lifespan (app :FastAPI ):


    init_db ()

    # Simulation runs accumulate on every click, so old ones are dropped at
    # startup rather than left to grow the database across a demo afternoon.
    _prune_simulation_runs ()
    _prune_live_sessions ()
    yield


def _prune_simulation_runs ()->None :
    from application .persistence import SessionLocal
    from application .simulation import store

    db =SessionLocal ()
    try :
        store .prune (db )
    finally :
        db .close ()


def _prune_live_sessions ()->None :
    from application.persistence import SessionLocal
    from application.operations.live_session import prune_sessions

    db =SessionLocal ()
    try:
        prune_sessions (db )
    finally:
        db .close ()


app =FastAPI (
title ="Payment Recovery API",
description ="FastAPI backend orchestrating LLM-driven payment recovery workflows.",
version ="0.1.0",
lifespan =lifespan ,
)



app .add_middleware (
CORSMiddleware ,
allow_origins =settings .cors_origins_list ,
allow_credentials =True ,
allow_methods =["*"],
allow_headers =["*"],
)

# Register routers explicitly so the public API surface is easy to audit and extend.
app .include_router (health_api .router ,prefix ="/api/v1")
app .include_router (webhook_api .router ,prefix ="/api/v1")
app .include_router (metrics_api .router ,prefix ="/api/v1")
app .include_router (router_api .router ,prefix ="/api/v1")
app .include_router (stream_api .router ,prefix ="/api/v1")
app .include_router (live_api .router ,prefix ="/api/v1")
app .include_router (transaction_api .router ,prefix ="/api/v1")
app .include_router (policy_api .router ,prefix ="/api/v1")
app .include_router (simulation_api .router ,prefix ="/api/v1")
app .include_router (admin_api .router ,prefix ="/api/v1")
app .include_router (assistant_api .router ,prefix ="/api/v1")
app .include_router (tracker_api .router ,prefix ="/api/v1")


@app .get ("/")
def root ():
    return {"message":"Payment recovery API is operational and running. Refer to /docs for API documentation."}
