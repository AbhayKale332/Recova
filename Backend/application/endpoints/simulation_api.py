"""HTTP surface for the what-if simulator.

The console's first screen is built on these: a user picks or fills in a
scenario, runs it, and watches the real engine work the book. Everything the
screen shows about *why* comes back over this stream.
"""

import json
from typing import Any

from fastapi import APIRouter ,Depends ,HTTPException ,Query ,status
from fastapi .responses import StreamingResponse
from pydantic import BaseModel ,Field ,model_validator
from sqlalchemy .orm import Session

from application .persistence import get_db
from application .simulation import store
from application .simulation .runner import DEFAULT_CONCURRENCY ,MAX_CONCURRENCY ,run
from application .simulation .scenario import SAMPLE_SCENARIOS ,Scenario

router =APIRouter (prefix ="/simulate",tags =["simulation"])

# Same SSE framing as the other streams in this service.
_SSE_HEADERS ={
"Cache-Control":"no-cache",
"Connection":"keep-alive",
"X-Accel-Buffering":"no",
}


def _sse (event :str ,data :dict [str ,Any ])->str :
    return f"event: {event }\ndata: {json .dumps (data ,default =str )}\n\n"


class SimulateBody (BaseModel ):
    scenario :Scenario
    concurrency :int =Field (DEFAULT_CONCURRENCY ,ge =1 ,le =MAX_CONCURRENCY )


class SaveScenarioBody (BaseModel ):
    slug :str =Field (min_length =1 ,max_length =80 ,pattern =r"^[a-z0-9][a-z0-9-]*$")
    name :str =Field (min_length =1 ,max_length =80 )
    description :str =Field ("",max_length =240 )
    payload :dict [str ,Any ]|None =None
    scenario :Scenario |None =None

    @model_validator (mode ="after")
    def _validate_payload (self )->"SaveScenarioBody":
        if self .payload is None and self .scenario is None :
            raise ValueError ("payload is required")
        raw =self .payload if self .payload is not None else self .scenario .model_dump (mode ="json")
        self .payload =Scenario .model_validate (raw ).model_dump (mode ="json")
        return self


@router .get ("/scenarios")
def list_scenarios (db :Session =Depends (get_db ))->dict :
    """The one-click sample scenarios.

    Each preset is chosen to make a different guardrail visible, so a demo can
    click through them instead of filling in a form under time pressure.
    """
    presets =[
    {"key":key ,"name":sc .name ,"description":sc .description ,"scenario":sc .model_dump (mode ="json")}
    for key ,sc in SAMPLE_SCENARIOS .items ()
    ]
    return {"presets":presets ,"saved":store .list_scenarios (db )}


@router .post ("/scenarios")
def save_scenario (payload :SaveScenarioBody ,db :Session =Depends (get_db ))->dict :
    return store .save_scenario (
    db ,payload .slug ,payload .name ,payload .description ,payload .payload or {}
    )


@router .delete ("/scenarios/{slug}")
def delete_scenario (slug :str ,db :Session =Depends (get_db ))->dict :
    if not store .delete_scenario (db ,slug ):
        raise HTTPException (
        status_code =status .HTTP_404_NOT_FOUND ,
        detail =f"Unknown saved scenario: {slug }",
        )
    return {"slug":slug ,"deleted":True }


@router .post ("/batch")
def simulate_batch (payload :SimulateBody )->StreamingResponse :
    """Run a scenario through the real recovery engine and stream the result.

    Events: ``start`` → (``case`` | ``progress``)* → ``complete``. Progress is
    coalesced rather than emitted per case, so the client gets a readable rate
    instead of a flood.
    """

    async def event_stream ():
        async for event ,data in run (payload .scenario ,concurrency =payload .concurrency ):
            yield _sse (event ,data )

    return StreamingResponse (
    event_stream (),media_type ="text/event-stream",headers =_SSE_HEADERS
    )


@router .get ("/runs")
def list_runs (db :Session =Depends (get_db ))->dict :
    return {"runs":store .list_runs (db )}


@router .get ("/runs/{run_id}")
def get_run (run_id :str ,db :Session =Depends (get_db ))->dict :
    """Reload a finished run without executing it again."""
    result =store .replay (db ,run_id )
    if result is None :
        raise HTTPException (
        status_code =status .HTTP_404_NOT_FOUND ,
        detail =f"Unknown simulation run: {run_id }",
        )
    return result


@router .delete ("/runs/{run_id}")
def delete_run (run_id :str ,db :Session =Depends (get_db ))->dict :
    removed =store .delete_run (db ,run_id )
    if not removed :
        raise HTTPException (
        status_code =status .HTTP_404_NOT_FOUND ,
        detail =f"Unknown simulation run: {run_id }",
        )
    return {"run_id":run_id ,"deleted":removed }


@router .post ("/prune")
def prune_runs (
keep :int =Query (store .KEEP_RUNS ,ge =0 ,le =50 ),
db :Session =Depends (get_db ),
)->dict :
    """Drop all but the newest ``keep`` runs."""
    return {"pruned":store .prune (db ,keep =keep )}
