"""Rupee amounts spelled out in words for text a TTS voice actually speaks.

ElevenLabs reads "₹5,000" as disconnected characters ("R S 5 0 0 0") rather
than as a number - a real voice-call transcript showed exactly that. Anything
handed to Vapi/ElevenLabs as speech must say the amount in words instead.
"""

from application.operations.speech_format import amount_to_words_en, speakable


def test_amount_to_words_small_number():
    assert amount_to_words_en(5000) == "Five Thousand"


def test_amount_to_words_single_digit():
    assert amount_to_words_en(2) == "Two"


def test_amount_to_words_with_hundreds():
    assert amount_to_words_en(1234) == "One Thousand Two Hundred Thirty Four"


def test_amount_to_words_lakh():
    assert amount_to_words_en(115000) == "One Lakh Fifteen Thousand"


def test_amount_to_words_crore():
    assert amount_to_words_en(12345678) == "One Crore Twenty Three Lakh Forty Five Thousand Six Hundred Seventy Eight"


def test_amount_to_words_exact_round_thousand():
    assert amount_to_words_en(1000) == "One Thousand"


def test_amount_to_words_zero():
    assert amount_to_words_en(0) == "Zero"


def test_amount_to_words_rounds_paise():
    assert amount_to_words_en(4999.6) == "Five Thousand"


def test_speakable_replaces_a_comma_formatted_rupee_amount():
    text = "Aapke ₹5,000 payment mein ek technical glitch aa gaya tha."
    assert speakable(text) == "Aapke Rupees Five Thousand payment mein ek technical glitch aa gaya tha."


def test_speakable_replaces_every_occurrence():
    text = "Aapka ₹2 test authorization. Salary date pe ₹115,000 cut ho jayega."
    result = speakable(text)
    assert "₹" not in result
    assert "Rupees Two" in result
    assert "Rupees One Lakh Fifteen Thousand" in result


def test_speakable_leaves_text_without_a_rupee_symbol_unchanged():
    text = "Haan theek hai, bhej do."
    assert speakable(text) == text


def test_speakable_handles_a_decimal_rupee_amount():
    text = "Amount: ₹115,000.00"
    assert speakable(text) == "Amount: Rupees One Lakh Fifteen Thousand"
