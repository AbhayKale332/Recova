"""Lazy Google Gemini integration used by advisory diagnosis and message generation."""

from google import genai
from google .genai import types

from application .settings import settings
from application .operations .diagnosis_service import DiagnosisEngine ,GenerateFn


def build_generate (api_key :str |None =None ,model :str |None =None )->GenerateFn :
    client =genai .Client (api_key =api_key or settings .gemini_api_key )
    model_name =model or settings .gemini_model

    def generate (prompt :str )->str :
        response =client .models .generate_content (
        model =model_name ,
        contents =prompt ,



        config =types .GenerateContentConfig (
        response_mime_type ="application/json",
        automatic_function_calling =types .AutomaticFunctionCallingConfig (disable =True ),
        ),
        )
        return response .text or ""

    return generate


def build_text_generate (api_key :str |None =None ,model :str |None =None )->GenerateFn :
    """A plain-text ``generate(prompt) -> str`` for message/voice drafting.

    Unlike the diagnosis generator this does not force JSON — the caller wants a
    natural WhatsApp/voice line. Uses the cheap draft model by default.
    """
    client =genai .Client (api_key =api_key or settings .gemini_api_key )
    model_name =model or settings .gemini_draft_model

    def generate (prompt :str )->str :
        response =client .models .generate_content (
        model =model_name ,
        contents =prompt ,
        config =types .GenerateContentConfig (
        automatic_function_calling =types .AutomaticFunctionCallingConfig (disable =True ),
        ),
        )
        return response .text or ""

    return generate


def default_diagnosis_engine ()->DiagnosisEngine :
    """Diagnosis engine backed by the live Gemini model from settings."""
    return DiagnosisEngine (generate =build_generate ())


def _openai_generate (model :str |None =None )->GenerateFn :
    """Strong tier over OpenAI.

    Imported inside the function so ``openai`` stays an optional dependency:
    nothing here is required unless ``LLM_PROVIDER=openai`` is actually set.
    """
    from openai import OpenAI

    client =OpenAI (api_key =settings .openai_api_key )
    model_name =model or settings .openai_model

    def generate (prompt :str )->str :
        response =client .chat .completions .create (
        model =model_name ,
        messages =[{"role":"user","content":prompt }],
        response_format ={"type":"json_object"},
        )
        return response .choices [0 ].message .content or ""

    return generate


def build_strong_generate ()->GenerateFn :
    """The strong JSON-mode tier, from whichever provider is configured.

    Provider selection lives here alone so the call sites never learn which
    vendor they are talking to. Every one of them already falls back to a
    deterministic path when the model fails, so a misconfigured provider degrades
    the wording rather than the behaviour.
    """
    if settings .llm_provider .lower ()=="openai":
        return _openai_generate ()
    return build_generate (model =settings .gemini_strong_model )
