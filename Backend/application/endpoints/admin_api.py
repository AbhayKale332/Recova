"""Administrative endpoints for deterministic batch initialization and operator support."""

import hmac

from fastapi import APIRouter ,Depends ,Header ,HTTPException ,status
from sqlalchemy .orm import Session

from application .persistence import get_db
from application .operations .batch_seed import seed_batch
from application .settings import settings

router =APIRouter (prefix ="/admin",tags =["admin"])


def require_admin_token (x_admin_token :str |None =Header (default =None ))->None :
    """Gate the destructive admin routes behind a shared secret.

    ``seed_batch`` truncates every table, bypassing the append-only audit
    guards via bulk delete, so this **fails closed**: with no ``ADMIN_TOKEN``
    configured the route is unavailable rather than open. A deployment that
    forgets the variable loses its reset button; it does not hand that button
    to the internet.
    """
    expected =settings .admin_token
    if not expected :
        raise HTTPException (
        status_code =status .HTTP_404_NOT_FOUND ,
        detail ="Admin routes are disabled. Set ADMIN_TOKEN to enable them.",
        )
    # Constant-time comparison, matching the webhook signature check.
    if not x_admin_token or not hmac .compare_digest (x_admin_token ,expected ):
        raise HTTPException (
        status_code =status .HTTP_401_UNAUTHORIZED ,
        detail ="Invalid or missing X-Admin-Token header.",
        )


@router .post ("/seed",dependencies =[Depends (require_admin_token )])
def seed (db :Session =Depends (get_db ))->dict :
    result =seed_batch (db )
    return {"seeded":result .seeded ,"by_state":result .by_state }
