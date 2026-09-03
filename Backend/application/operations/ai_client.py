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
