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

# Hindi numerals 0-99 are irregular (not simple tens+ones concatenation), so
# unlike the English table above this is a direct lookup, not built from
# smaller pieces.
_HI_WORDS = [
    "शून्य", "एक", "दो", "तीन", "चार", "पांच", "छह", "सात", "आठ", "नौ",
    "दस", "ग्यारह", "बारह", "तेरह", "चौदह", "पंद्रह", "सोलह", "सत्रह", "अठारह", "उन्नीस",
    "बीस", "इक्कीस", "बाईस", "तेईस", "चौबीस", "पच्चीस", "छब्बीस", "सत्ताईस", "अट्ठाईस", "उनतीस",
    "तीस", "इकतीस", "बत्तीस", "तैंतीस", "चौंतीस", "पैंतीस", "छत्तीस", "सैंतीस", "अड़तीस", "उनतालीस",
    "चालीस", "इकतालीस", "बयालीस", "तैंतालीस", "चौंतालीस", "पैंतालीस", "छियालीस", "सैंतालीस", "अड़तालीस", "उनचास",
    "पचास", "इक्यावन", "बावन", "तिरेपन", "चौवन", "पचपन", "छप्पन", "सत्तावन", "अट्ठावन", "उनसठ",
    "साठ", "इकसठ", "बासठ", "तिरेसठ", "चौंसठ", "पैंसठ", "छियासठ", "सड़सठ", "अड़सठ", "उनहत्तर",
    "सत्तर", "इकहत्तर", "बहत्तर", "तिहत्तर", "चौहत्तर", "पचहत्तर", "छिहत्तर", "सतहत्तर", "अठहत्तर", "उनासी",
    "अस्सी", "इक्यासी", "बयासी", "तिरासी", "चौरासी", "पचासी", "छियासी", "सत्तासी", "अट्ठासी", "नवासी",
    "नब्बे", "इक्यानवे", "बानवे", "तिरानवे", "चौरानवे", "पंचानवे", "छियानवे", "सत्तानवे", "अट्ठानवे", "निन्यानवे",
]


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


def _hi_two_digit_words(n: int) -> str:
    return _HI_WORDS[n]


def _hi_three_digit_words(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append(f"{_HI_WORDS[hundreds]} सौ")
    if rest:
        parts.append(_hi_two_digit_words(rest))
    return " ".join(parts)


def amount_to_words_hi(amount: float | int) -> str:
    """Spell out a whole-rupee amount in Hindi (Devanagari), same Indian
    numbering grouping (हज़ार, लाख, करोड़) as ``amount_to_words_en``."""
    n = int(round(amount))
    if n <= 0:
        return "शून्य"
    crore, n = divmod(n, 1_00_00_000)
    lakh, n = divmod(n, 1_00_000)
    thousand, n = divmod(n, 1_000)
    hundreds_rest = n
    parts = []
    if crore:
        parts.append(f"{_hi_three_digit_words(crore)} करोड़")
    if lakh:
        parts.append(f"{_hi_three_digit_words(lakh)} लाख")
    if thousand:
        parts.append(f"{_hi_three_digit_words(thousand)} हज़ार")
    if hundreds_rest:
        parts.append(_hi_three_digit_words(hundreds_rest))
    return " ".join(parts)


def speakable(text: str, locale: str = "en") -> str:
    """Replace every "₹<amount>" in ``text`` with its spoken word form.

    Used for any text handed to a real TTS voice (Vapi/ElevenLabs) - never for
    text that is only displayed, where the currency-formatted figure is the
    correct and expected presentation. ``locale="hi"`` spells the amount (and
    the "Rupees" prefix) in Hindi, since a Hindi TTS pass reading English
    number words mid-sentence is exactly the same disconnected-character
    problem this function exists to avoid.
    """
    words_fn = amount_to_words_hi if locale == "hi" else amount_to_words_en
    prefix = "रुपये" if locale == "hi" else "Rupees"

    def _replace(match: re.Match[str]) -> str:
        digits = match.group(1).replace(",", "")
        return f"{prefix} {words_fn(float(digits))}"

    return _RUPEE_AMOUNT.sub(_replace, text)
