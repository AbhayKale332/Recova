"""FastAPI application entry point and router registration for the payment recovery service."""

import logging
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI ,Request
from fastapi .middleware .cors import CORSMiddleware
from fastapi .responses import JSONResponse

from application .settings import settings
from application .persistence import init_db
from application .endpoints import (
admin_api ,
    assistant_api ,
    live_api ,
health_api ,
metrics_api ,
repayment_api ,
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
    _backfill_policy_actions ()

    # Simulation runs accumulate on every click, so old ones are dropped at
    # startup rather than left to grow the database across a demo afternoon.
    _prune_simulation_runs ()
    _prune_live_sessions ()

    import asyncio
    from application .operations import deadline_sweeper

    sweeper_task =asyncio .create_task (deadline_sweeper .run_forever ())
    try :
        yield
    finally :
        sweeper_task .cancel ()
        try :
            await sweeper_task
        except asyncio .CancelledError :
            pass


def _backfill_policy_actions ()->None :
    from application .persistence import SessionLocal
    from application .operations import policy_repository
    import logging

    db =SessionLocal ()
    try :
        added =policy_repository .backfill_default_actions (db )
        if added :
            logging .getLogger (__name__ ).info ("Backfilled merchant policy actions: %s",added )
    finally :
        db .close ()


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



# A global cap on billable API calls per IST day. Registered before the CORS
# middleware so CORS stays the outermost layer and a 429 still carries the
# Access-Control-* headers a browser needs to read the error.
_RATE_LIMIT_EXEMPT_PREFIXES =("/api/v1/health","/api/v1/webhooks")


def _seconds_until_ist_midnight ()->int :
    from application .helpers import now_ist

    now =now_ist ()
    next_midnight =(now +timedelta (days =1 )).replace (
    hour =0 ,minute =0 ,second =0 ,microsecond =0
    )
    return max (1 ,int ((next_midnight -now ).total_seconds ()))


@app .middleware ("http")
async def _enforce_daily_request_cap (request :Request ,call_next ):
    if not settings .rate_limit_enabled or request .method =="OPTIONS":
        return await call_next (request )

    path =request .url .path
    if not path .startswith ("/api/")or path .startswith (_RATE_LIMIT_EXEMPT_PREFIXES ):
        return await call_next (request )

    from application .persistence import SessionLocal
    from application .operations .rate_limiter import check_and_increment

    db =SessionLocal ()
    try :
        verdict =check_and_increment (db ,settings .daily_request_limit )
    except Exception :
        logging .getLogger (__name__ ).exception ("rate limiter failed; allowing request")
        return await call_next (request )
    finally :
        db .close ()

    if not verdict .allowed :
        return JSONResponse (
        status_code =429 ,
        content ={
        "detail":f"Daily API request limit reached ({verdict .limit }/day). Resets at 00:00 IST."
        },
        headers ={
        "X-RateLimit-Limit":str (verdict .limit ),
        "X-RateLimit-Remaining":"0",
        "Retry-After":str (_seconds_until_ist_midnight ()),
        },
        )

    response =await call_next (request )
    response .headers ["X-RateLimit-Limit"]=str (verdict .limit )
    response .headers ["X-RateLimit-Remaining"]=str (verdict .remaining )
    return response


app .add_middleware (
CORSMiddleware ,
allow_origins =settings .cors_origins_list ,
allow_credentials =True ,
allow_methods =["*"],
allow_headers =["*"],
expose_headers =["X-RateLimit-Limit","X-RateLimit-Remaining","Retry-After"],
)

# Register routers explicitly so the public API surface is easy to audit and extend.
app .include_router (health_api .router ,prefix ="/api/v1")
app .include_router (webhook_api .router ,prefix ="/api/v1")
app .include_router (metrics_api .router ,prefix ="/api/v1")
app .include_router (repayment_api .router ,prefix ="/api/v1")
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
