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
    # Opt into the server-side Razorpay MCP dispatch transport explicitly.
    razorpay_mcp_enabled :bool =False
    # Official hosted Razorpay MCP endpoint; Streamable HTTP is preferred.
    razorpay_mcp_url :str ="https://mcp.razorpay.com/mcp"
    # Keep the remote transport restricted to test keys unless an operator explicitly overrides it.
    razorpay_mcp_allow_live_keys :bool =False
    # Hard wall-clock limit for one MCP connection/call attempt.
    razorpay_mcp_timeout_s :float =5.0



    gemini_api_key :str =""

    # Model names are grouped by router tier rather than by call site. The old
    # aliases below remain for existing .env files and direct wrapper callers.
    gemini_nano_model :str ="gemini-flash-lite-latest"
    gemini_mini_model :str ="gemini-3.6-flash"
    gemini_full_model :str ="gemini-3-pro"
    gemini_model :str ="gemini-3.6-flash"
    gemini_draft_model :str ="gemini-flash-lite-latest"


    # The strong tier. Only the operator assistant uses it: that is the one call
    # site doing strict structured extraction over the whole injected transaction
    # catalog, so it is the only one where model quality changes the outcome
    # rather than the phrasing. Diagnosis and drafting stay on the cheap tiers,
    # because batch drafting dominates token spend.
    gemini_strong_model :str ="gemini-3-pro"

    # "openai" | "gemini". This is a manual provider override; otherwise the
    # router tries OpenAI first and falls through to Gemini.
    llm_provider :str ="openai"
    openai_api_key :str =""
    openai_nano_model :str ="gpt-5.4-nano"
    openai_mini_model :str ="gpt-5.4-mini"
    openai_full_model :str ="gpt-5.4"
    openai_model :str ="gpt-5"

    router_stakes_threshold_inr :float =25000
    # The free daily quota requires opting into sharing that traffic with
    # OpenAI — this is a real product decision, not a footnote.
    openai_free_tier :bool =False




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
