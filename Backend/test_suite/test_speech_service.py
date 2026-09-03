"""Voice output — ElevenLabs TTS with a browser fallback."""

from application .operations .speech_service import synthesize


def test_no_key_returns_none (monkeypatch ):

    monkeypatch .setattr ("application.operations.speech_service.settings.elevenlabs_api_key","",raising =False )
    assert synthesize ("hello")is None


def test_empty_text_returns_none ():
    assert synthesize ("   ",api_key ="k")is None


def test_tts_endpoint_204_without_key (client ,monkeypatch ):

    monkeypatch .setattr ("application.operations.speech_service.settings.elevenlabs_api_key","",raising =False )
    resp =client .post ("/api/v1/assistant/tts",json ={"text":"Recovered Acme's invoice."})
    assert resp .status_code ==204
