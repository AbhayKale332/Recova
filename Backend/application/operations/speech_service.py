"""ElevenLabs speech synthesis with a browser-voice fallback signal."""

from __future__ import annotations

import logging

import httpx

from application .settings import settings

logger =logging .getLogger (__name__ )

_ENDPOINT ="https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"



_FALLBACK_VOICE ="EXAVITQu4vr4xnSDxMaL"


def _speak (voice :str ,text :str ,key :str ,model :str )->tuple [int ,bytes ]:
    resp =httpx .post (
    _ENDPOINT .format (voice_id =voice ),
    headers ={"xi-api-key":key ,"content-type":"application/json"},
    json ={
    "text":text ,
    "model_id":model ,
    "voice_settings":{"stability":0.4 ,"similarity_boost":0.85 },
    },
    timeout =30.0 ,
    )
    return resp .status_code ,resp .content if resp .status_code ==200 else resp .text .encode ()[:200 ]


def synthesize (
text :str ,
*,
api_key :str |None =None ,
voice_id :str |None =None ,
model :str |None =None ,
)->bytes |None :
    key =api_key if api_key is not None else settings .elevenlabs_api_key
    if not key or not text .strip ():
        return None
    voice =voice_id or settings .elevenlabs_voice_id
    mdl =model or settings .elevenlabs_model
    try :
        status ,body =_speak (voice ,text ,key ,mdl )
        if status ==200 :
            return body
        logger .warning ("ElevenLabs speech synthesis failed for voice %s (%s): %s",voice ,status ,body [:180 ])

        if status in (401 ,402 ,403 ,404 )and voice !=_FALLBACK_VOICE :
            status ,body =_speak (_FALLBACK_VOICE ,text ,key ,mdl )
            if status ==200 :
                return body
            logger .warning ("ElevenLabs fallback voice failed (%s): %s",status ,body [:180 ])
    except Exception as exc :
        logger .warning ("Speech synthesis failed (%s); browser speech will be used as the fallback.",exc )
    return None
