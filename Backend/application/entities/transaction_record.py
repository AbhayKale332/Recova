"""Persistence model for transaction identity, lifecycle, amount, and recovery metadata."""

from sqlalchemy import (
CheckConstraint ,
Column ,
DateTime ,
Enum ,
Integer ,
JSON ,
String ,
)
from sqlalchemy .orm import relationship

from application .persistence import Base
from application .constants import TransactionLifecycleState
from application .protection import EncryptedString
from application .helpers import utcnow


class TransactionState (Base ):
    __tablename__ ="transaction_states"

    id =Column (Integer ,primary_key =True ,index =True )
    transaction_id =Column (String (64 ),unique =True ,index =True ,nullable =False )


    razorpay_payment_id =Column (String (64 ),index =True ,nullable =False )

    failure_class =Column (Integer ,nullable =False )
    current_state =Column (
    Enum (TransactionLifecycleState ,validate_strings =True ),
    default =TransactionLifecycleState .PENDING ,
    nullable =False ,
    )
    retry_count =Column (Integer ,default =0 ,nullable =False )
    max_retries =Column (Integer ,default =3 ,nullable =False )
    merchant_id =Column (String (64 ),nullable =False )

    customer_contact =Column (EncryptedString (256 ),nullable =False )


    amount_minor =Column (Integer ,nullable =False )
    currency =Column (String (3 ),default ="INR",nullable =False )
    metadata_json =Column (JSON ,nullable =True )
    created_at =Column (DateTime (timezone =True ),default =utcnow ,nullable =False )
    updated_at =Column (
    DateTime (timezone =True ),default =utcnow ,onupdate =utcnow ,nullable =False
    )

    audit_trails =relationship ("AuditTrail",backref ="transaction_state")

    __table_args__ =(
    CheckConstraint (
    "failure_class BETWEEN 1 AND 4",name ="ck_failure_class_range"
    ),
    CheckConstraint ("retry_count >= 0",name ="ck_retry_count_non_negative"),
    CheckConstraint ("amount_minor >= 0",name ="ck_amount_non_negative"),
    )
