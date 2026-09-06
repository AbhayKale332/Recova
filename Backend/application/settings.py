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


    # Global cap on billable API calls per IST calendar day, shared across all
    # callers. Health checks, CORS preflight, the docs routes and inbound
    # Razorpay webhooks are exempt. Set rate_limit_enabled=false to turn off.
    rate_limit_enabled :bool =True
    daily_request_limit :int =200


    encryption_key :str =""

    # Shared secret for the destructive admin routes. POST /admin/seed
    # truncates every table, so the gate fails closed: empty means the route is
    # disabled outright, not open. Send it as the X-Admin-Token header.
    admin_token :str =""


    razorpay_key_id :str =""
    razorpay_key_secret :str =""
    razorpay_webhook_secret :str =""
    # Opt into the server-side Razorpay MCP dispatch transport explicitly.
    razorpay_mcp_enabled :bool =False
    # Local Docker stdio is the default; hosted Streamable HTTP remains available as a fallback.
    razorpay_mcp_transport :str ="stdio"
    razorpay_mcp_docker_image :str ="razorpay-mcp-server:latest"
    razorpay_mcp_docker_command :str ="docker"
    # Official hosted Razorpay MCP endpoint; Streamable HTTP is preferred.
    razorpay_mcp_url :str ="https://mcp.razorpay.com/mcp"
    # Keep the remote transport restricted to test keys unless an operator explicitly overrides it.
    razorpay_mcp_allow_live_keys :bool =False
    # Hard wall-clock limit for one MCP connection/call attempt.
    razorpay_mcp_timeout_s :float =5.0

    # A partial-plan's balance deadline, absent an explicit deadline_days from
    # the model. The sweeper (Part 5) reads this too.
    partial_plan_default_days :int =14
    # > 0 overrides partial_plan_default_days with a deadline this many
    # *seconds* out instead of days - a 14-day deadline cannot be demonstrated
    # in a two-minute video. Set to 45 for a recording; leave 0 otherwise.
    partial_plan_demo_seconds :int =0
    # How often the deadline sweeper (Part 5) wakes up to check for a passed
    # partial-payment deadline with a balance still outstanding.
    deadline_sweep_seconds :int =30

    # How often a live session polls Razorpay for a minted artifact's payment
    # status. There is no webhook reachable from localhost in the demo, so
    # this poll is what notices a completed checkout and reflects it back
    # into the WhatsApp thread.
    payment_poll_seconds :float =4.0



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
    vapi_public_key :str =""
    vapi_assistant_id :str =""
    vapi_phone_number_id :str =""
    vapi_webhook_secret :str =""
    vapi_allowed_numbers :str =""

    voice_agent_name :str ="Rekha"
    voice_agent_locale :str ="hi"
    vapi_transcriber_provider :str ="deepgram"
    vapi_transcriber_model :str ="nova-3"
    vapi_transcriber_language :str ="multi"
    # Ambient call-center room tone so Rekha doesn't sound like she's calling
    # from total silence - "off" disables it. Vapi's built-in options.
    vapi_background_sound :str ="office"

    model_config =SettingsConfigDict (env_file =".env",extra ="ignore")

    @property
    def cors_origins_list (self )->list [str ]:
        return [origin .strip ()for origin in self .cors_origins .split (",")if origin .strip ()]

    @property
    def vapi_allowed_numbers_list (self )->list [str ]:
        if not self .vapi_allowed_numbers :
            return []
        return [num .strip ()for num in self .vapi_allowed_numbers .split (",")if num .strip ()]


settings =Settings ()
