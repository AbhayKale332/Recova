"""Centralized runtime configuration for database, security, provider integrations, and CORS."""

from pathlib import Path

from pydantic_settings import BaseSettings ,SettingsConfigDict




# Resolve paths from this module so startup behavior is independent of the working directory.
BACKEND_DIR =Path (__file__ ).resolve ().parent .parent


# Environment-backed defaults keep local development deterministic while deployments remain configurable.
class Settings (BaseSettings ):
    app_name :str ="Payment Recovery API"
    database_url :str =f"sqlite:///{BACKEND_DIR /'recovery_engine.db'}"



    cors_origins :str ="http://localhost:3000"


    encryption_key :str =""


    razorpay_key_id :str =""
    razorpay_key_secret :str =""
    razorpay_webhook_secret :str =""



    gemini_api_key :str =""
    gemini_model :str ="gemini-3.6-flash"



    gemini_draft_model :str ="gemini-flash-lite-latest"




    elevenlabs_api_key :str =""
    elevenlabs_voice_id :str ="EXAVITQu4vr4xnSDxMaL"
    elevenlabs_model :str ="eleven_multilingual_v2"



    live_mode :bool =False




    twilio_account_sid :str =""
    twilio_auth_token :str =""
    twilio_api_key_sid :str =""
    twilio_api_key_secret :str =""
    twilio_whatsapp_from :str ="whatsapp:+14155238886"


    vapi_api_key :str =""

    model_config =SettingsConfigDict (env_file =".env",extra ="ignore")

    @property
    def cors_origins_list (self )->list [str ]:
        return [origin .strip ()for origin in self .cors_origins .split (",")if origin .strip ()]


settings =Settings ()
