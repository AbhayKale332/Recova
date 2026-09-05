"""Tests for transient Vapi assistant configuration and guardrail integration."""

from application.entities import TransactionState
from application.operations.voice_agent import build_assistant
from application.settings import settings


def test_build_assistant_config_structure():
    txn = TransactionState(
        id=1,
        transaction_id="txn_test_voice",
        failure_class=1,
        merchant_id="m1",
        customer_contact="+919999999999",
        amount_minor=150000,
        metadata_json={"customer_name": "Rohan Sharma"},
    )
    bounds = {
        "voice": {"used": 1, "cap": 2, "exhausted": False},
        "retries": {"used": 0, "cap": 3, "exhausted": False},
    }

    config = build_assistant(txn, locale="en", bounds=bounds)

    assert config["name"] == "recova-assistant-txn_test_voice"
    assert config["maxDurationSeconds"] == 180

    # Voice configuration check
    voice = config["voice"]
    assert voice["provider"] == "11labs"
    assert voice["voiceId"] == settings.elevenlabs_voice_id
    assert voice["model"] == settings.elevenlabs_model

    # Model configuration check
    model = config["model"]
    assert model["provider"] in ("openai", "google")
    assert model["model"]
    assert "Rohan Sharma" in model["systemPrompt"]
    assert "₹1,500.00" in model["systemPrompt"]
    assert "one voice attempt remains" in model["systemPrompt"]

    # First message check
    assert "Namaste Rohan" in config["firstMessage"]


def test_build_assistant_zero_attempts_remaining():
    txn = TransactionState(
        id=2,
        transaction_id="txn_test_voice_2",
        failure_class=2,
        merchant_id="m1",
        customer_contact="+919999999999",
        amount_minor=250000,
        metadata_json={"customer_name": "Priya Verma"},
    )
    bounds = {
        "voice": {"used": 2, "cap": 2, "exhausted": True},
    }

    config = build_assistant(txn, locale="hi", bounds=bounds)
    assert "0 voice attempts remain" in config["model"]["systemPrompt"]
    assert "Hindi / Hinglish" in config["model"]["systemPrompt"]
