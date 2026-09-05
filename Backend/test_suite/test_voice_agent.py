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

    assert config["name"] == "recova-txn_test_voice"
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
    assert "Rupees One Thousand Five Hundred" in model["systemPrompt"]
    assert "one voice attempt remains" in model["systemPrompt"]

    # First message check
    assert "Namaste Rohan" in config["firstMessage"]


def test_build_assistant_never_hands_a_rupee_symbol_to_the_voice():
    # ElevenLabs reads "₹5,000" as disconnected characters ("R S 5 0 0 0")
    # rather than as a number - both the scripted opening and the system
    # prompt fact the model reads from must say the amount in words instead.
    txn = TransactionState(
        id=4,
        transaction_id="txn_test_voice_speakable",
        failure_class=2,
        merchant_id="m1",
        customer_contact="+919999999999",
        amount_minor=500000,
        metadata_json={"customer_name": "Abhay"},
    )
    config = build_assistant(txn, locale="en", bounds={})
    assert "₹" not in config["firstMessage"]
    assert "₹" not in config["model"]["systemPrompt"]
    assert "Rupees Five Thousand" in config["model"]["systemPrompt"]


def test_build_assistant_name_never_exceeds_vapis_40_character_limit():
    # Real live-session transaction ids ("sim_" + an 8-char run-id slice +
    # "_custom_0000") push "recova-assistant-<id>" past 40 characters, which
    # Vapi's API rejects outright with 'assistant.name must be shorter than or
    # equal to 40 characters' - the call never starts, and the failure surfaces
    # to the customer-facing call stage as that raw validation message.
    txn = TransactionState(
        id=3,
        transaction_id="sim_live_8da12345_custom_0000",
        failure_class=1,
        merchant_id="m1",
        customer_contact="+919999999999",
        amount_minor=150000,
        metadata_json={"customer_name": "Asha Rao"},
    )
    config = build_assistant(txn, locale="en", bounds={})
    assert len(config["name"]) <= 40


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
