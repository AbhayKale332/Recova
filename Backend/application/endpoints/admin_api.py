"""Administrative endpoints for deterministic batch initialization and operator support."""

from fastapi import APIRouter ,Depends
from sqlalchemy .orm import Session

from application .persistence import get_db
from application .operations .batch_seed import seed_batch

router =APIRouter (prefix ="/admin",tags =["admin"])


@router .post ("/seed")
def seed (db :Session =Depends (get_db ))->dict :
    result =seed_batch (db )
    return {"seeded":result .seeded ,"by_state":result .by_state }
