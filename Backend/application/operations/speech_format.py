"""Rupee amounts spelled out in words, for text a TTS voice actually speaks.

Every other surface (WhatsApp, the case detail panel, the audit trail) shows
money as "₹5,000" - that is exactly right for reading. A voice call is
different: ElevenLabs reads "₹5,000" as disconnected characters ("R S 5 0 0
0") rather than as a number, so anything handed to Vapi as `firstMessage` or
a system prompt fact must say the amount in words instead.
"""

import re

_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = [
    "", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety",
]

_RUPEE_AMOUNT = re.compile(r"₹\s*([\d,]+(?:\.\d+)?)")


def _two_digit_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (f" {_ONES[ones]}" if ones else "")


def _three_digit_words(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append(f"{_ONES[hundreds]} Hundred")
    if rest:
        parts.append(_two_digit_words(rest))
    return " ".join(parts)


def amount_to_words_en(amount: float | int) -> str:
    """Spell out a whole-rupee amount using the Indian numbering system
    (thousand, lakh, crore) - how these amounts are actually spoken."""
    n = int(round(amount))
    if n <= 0:
        return "Zero"
    crore, n = divmod(n, 1_00_00_000)
    lakh, n = divmod(n, 1_00_000)
    thousand, n = divmod(n, 1_000)
    hundreds_rest = n
    parts = []
    if crore:
        parts.append(f"{_three_digit_words(crore)} Crore")
    if lakh:
        parts.append(f"{_three_digit_words(lakh)} Lakh")
    if thousand:
        parts.append(f"{_three_digit_words(thousand)} Thousand")
    if hundreds_rest:
        parts.append(_three_digit_words(hundreds_rest))
    return " ".join(parts)


def speakable(text: str) -> str:
    """Replace every "₹<amount>" in ``text`` with its spoken word form.

    Used for any text handed to a real TTS voice (Vapi/ElevenLabs) - never for
    text that is only displayed, where the currency-formatted figure is the
    correct and expected presentation.
    """

    def _replace(match: re.Match[str]) -> str:
        digits = match.group(1).replace(",", "")
        return f"Rupees {amount_to_words_en(float(digits))}"

    return _RUPEE_AMOUNT.sub(_replace, text)
