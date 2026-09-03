"""Serialized representation of transaction recovery state."""

from datetime import datetime
from typing import Any ,Dict ,Optional

from pydantic import BaseModel ,ConfigDict ,Field

from application .constants import FailureClass ,TransactionLifecycleState


class TransactionStateBase (BaseModel ):
    transaction_id :str
    razorpay_payment_id :str
    failure_class :FailureClass
    current_state :TransactionLifecycleState =TransactionLifecycleState .PENDING
    merchant_id :str
    customer_contact :str
    amount_minor :int =Field (ge =0 ,description ="Amount in the currency's minor unit (paise for INR)")
    currency :str ="INR"
    metadata_json :Optional [Dict [str ,Any ]]=None


class TransactionStateCreate (TransactionStateBase ):
    pass


class TransactionStateUpdate (BaseModel ):
    current_state :Optional [TransactionLifecycleState ]=None
    retry_count :Optional [int ]=Field (default =None ,ge =0 )
    metadata_json :Optional [Dict [str ,Any ]]=None


class TransactionStateResponse (TransactionStateBase ):
    model_config =ConfigDict (from_attributes =True )

    id :int
    retry_count :int
    max_retries :int
    created_at :datetime
    updated_at :datetime
