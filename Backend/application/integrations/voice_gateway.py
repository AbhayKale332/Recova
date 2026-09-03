"""Vapi voice adapter with a safe simulated mode when credentials are unavailable."""

import uuid

from application .integrations .adapter_base import DispatchResult
from application .settings import settings

_CHANNEL ="VOICE"


class VoiceAdapter :
    def __init__ (self ,live_mode :bool ,api_key :str |None =None ):
        self ._live =live_mode
        self ._api_key =settings .vapi_api_key if api_key is None else api_key

    def call (self ,to :str ,script :str )->DispatchResult :
        if not self ._live or not self ._api_key :
            detail =None if self ._api_key else "vapi_not_configured"
            return DispatchResult (
            _CHANNEL ,delivered =True ,simulated =True ,
            reference =f"sim_{uuid .uuid4 ().hex [:12 ]}",detail =detail ,
            )


        raise NotImplementedError ("Live Vapi voice calls are not wired yet.")
