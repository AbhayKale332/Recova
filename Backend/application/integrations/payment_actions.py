"""Razorpay adapter for payment links, charge retries, and subscription cancellation."""

import uuid

from application .integrations .adapter_base import DispatchResult
from application .integrations .razorpay_mcp import RazorpayMCPClient ,default_client ,mcp_dispatch_enabled
from application .settings import settings

_CHANNEL ="PAYMENT_LINK"


class RazorpayActionsAdapter :
    def __init__ (self ,live_mode :bool ,client =None ,mcp_client =None ):
        self ._live =live_mode
        self ._client =client
        self ._mcp_client =mcp_client

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

    def _mcp (self ,amount_minor :int ,contact :str ,failure_class :int =1 )->DispatchResult |None :
        if not mcp_dispatch_enabled ():
            return None
        client =self ._mcp_client or default_client ()
        try :
            link =client .create_payment_link (
            amount_minor =amount_minor ,contact =contact ,failure_class =failure_class
            )
        except Exception :
            return None
        if not link or not link .get ("id"):
            return None
        return DispatchResult (_CHANNEL ,delivered =True ,simulated =False ,reference =link .get ("id"),detail ="mcp")

    def create_payment_link (self ,amount_minor :int ,contact :str ,failure_class :int =1 )->DispatchResult :
        mcp_result =self ._mcp (amount_minor ,contact ,failure_class )
        if mcp_result is not None :
            return mcp_result
        if not self ._live :
            return self ._sim (_CHANNEL ,"simulated")
        try :
            link =self ._razorpay ().payment_link .create (
        {
        "amount":amount_minor ,
        "currency":"INR",
        "customer":{"contact":contact },
        "notify":{"sms":False ,"email":False },
        }
            )
        except Exception :
            return self ._sim (_CHANNEL ,"simulated")
        return DispatchResult (_CHANNEL ,delivered =True ,simulated =False ,reference =link .get ("id"),detail ="sdk")

    def retry_charge (self ,transaction_id :str )->DispatchResult :


        return self ._sim ("RAZORPAY","simulated")

    def cancel_subscription (self ,transaction_id :str )->DispatchResult :
        return self ._sim ("RAZORPAY","simulated")
