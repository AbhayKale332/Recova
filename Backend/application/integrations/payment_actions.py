"""Razorpay adapter for payment links, charge retries, and subscription cancellation."""

import uuid

from application .integrations .adapter_base import DispatchResult
from application .settings import settings

_CHANNEL ="PAYMENT_LINK"


class RazorpayActionsAdapter :
    def __init__ (self ,live_mode :bool ,client =None ):
        self ._live =live_mode
        self ._client =client

    def _razorpay (self ):
        if self ._client is None :
            import razorpay

            self ._client =razorpay .Client (
            auth =(settings .razorpay_key_id ,settings .razorpay_key_secret )
            )
        return self ._client

    def _sim (self ,channel :str ,detail :str )->DispatchResult :
        return DispatchResult (
        channel ,delivered =True ,simulated =True ,
        reference =f"sim_{uuid .uuid4 ().hex [:12 ]}",detail =detail ,
        )

    def create_payment_link (self ,amount_minor :int ,contact :str )->DispatchResult :
        if not self ._live :
            return self ._sim (_CHANNEL ,"payment_link")
        link =self ._razorpay ().payment_link .create (
        {
        "amount":amount_minor ,
        "currency":"INR",
        "customer":{"contact":contact },
        "notify":{"sms":False ,"email":False },
        }
        )
        return DispatchResult (_CHANNEL ,delivered =True ,simulated =False ,reference =link .get ("id"))

    def retry_charge (self ,transaction_id :str )->DispatchResult :


        return self ._sim ("RAZORPAY","retry_charge")

    def cancel_subscription (self ,transaction_id :str )->DispatchResult :
        return self ._sim ("RAZORPAY","cancel_subscription")
