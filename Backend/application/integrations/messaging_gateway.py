"""Twilio-backed WhatsApp delivery with an explicit simulation mode for local execution."""

import logging
import uuid

from application .integrations .adapter_base import DispatchResult
from application .settings import settings

logger =logging .getLogger (__name__ )

_CHANNEL ="WHATSAPP"


class WhatsAppAdapter :
    def __init__ (self ,live_mode :bool ,client =None ,from_ :str |None =None ):
        self ._live =live_mode
        self ._client =client
        self ._from =from_ or settings .twilio_whatsapp_from

    def _twilio (self ):
        if self ._client is None :
            from twilio .rest import Client

            if settings .twilio_api_key_sid :

                self ._client =Client (
                settings .twilio_api_key_sid ,
                settings .twilio_api_key_secret ,
                settings .twilio_account_sid ,
                )
            else :
                self ._client =Client (settings .twilio_account_sid ,settings .twilio_auth_token )
        return self ._client

    def send (self ,to :str ,body :str )->DispatchResult :
        if not self ._live :
            return DispatchResult (_CHANNEL ,delivered =True ,simulated =True ,reference =f"sim_{uuid .uuid4 ().hex [:12 ]}")

        try :
            message =self ._twilio ().messages .create (
            from_ =self ._from ,
            to =f"whatsapp:{to }",
            body =body ,
            )
        except Exception as exc :
            logger .warning ("Live WhatsApp delivery failed: %s",exc )
            return DispatchResult (_CHANNEL ,delivered =False ,simulated =False ,detail =str (exc ))
        return DispatchResult (_CHANNEL ,delivered =True ,simulated =False ,reference =message .sid )
