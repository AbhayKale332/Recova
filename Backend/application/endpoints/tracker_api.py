"""Endpoints for subscription and receivables tracker views."""

from datetime import date

from fastapi import APIRouter ,Depends
from pydantic import BaseModel ,Field
from sqlalchemy .orm import Session

from application .persistence import get_db
from application .operations .tracker_service import (
create_invoice ,
create_subscription ,
list_invoices ,
list_subscriptions ,
)

router =APIRouter (tags =["trackers"])


@router .get ("/subscriptions")
def get_subscriptions (db :Session =Depends (get_db ))->list [dict ]:
    return list_subscriptions (db )


class NewSubscription (BaseModel ):
    customer_name :str =Field (min_length =1 ,max_length =120 )
    plan :str =Field (min_length =1 ,max_length =80 )
    amount_inr :float =Field (gt =0 )
    next_debit_date :date
    salary_day :int =Field (default =1 ,ge =1 ,le =31 )


@router .post ("/subscriptions")
def add_subscription (body :NewSubscription ,db :Session =Depends (get_db ))->dict :
    return create_subscription (
    db ,
    customer_name =body .customer_name ,
    plan =body .plan ,
    amount_inr =body .amount_inr ,
    next_debit_date =body .next_debit_date .isoformat (),
    salary_day =body .salary_day ,
    )


@router .get ("/invoices")
def get_invoices (db :Session =Depends (get_db ))->list [dict ]:
    return list_invoices (db )


class NewInvoice (BaseModel ):
    buyer_name :str =Field (min_length =1 ,max_length =120 )
    amount_inr :float =Field (gt =0 )
    issue_date :date
    due_date :date
    terms :str =Field (default ="NET30",max_length =20 )


@router .post ("/invoices")
def add_invoice (body :NewInvoice ,db :Session =Depends (get_db ))->dict :
    return create_invoice (
    db ,
    buyer_name =body .buyer_name ,
    amount_inr =body .amount_inr ,
    issue_date =body .issue_date .isoformat (),
    due_date =body .due_date .isoformat (),
    terms =body .terms ,
    )
