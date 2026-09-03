"""Deterministic Hinglish Promise-to-Pay date extraction — the offline NER that
makes the B2B receivables class genuinely reactive to a customer's reply."""

from datetime import date

from application .operations .language_parser import extract_p2p_date

TODAY =date (2026 ,8 ,29 )


def test_extracts_tarikh_this_month ():

    assert extract_p2p_date ("5 tarikh ko kar denge",today =TODAY )=="2026-09-05"


def test_extracts_tarikh_still_ahead_this_month ():
    assert extract_p2p_date ("30 tareekh tak pakka",today =TODAY )=="2026-08-30"


def test_extracts_relative_kal_parso ():
    assert extract_p2p_date ("kal kar dunga",today =TODAY )=="2026-08-30"
    assert extract_p2p_date ("parso pakka",today =TODAY )=="2026-08-31"


def test_extracts_din_offset ():
    assert extract_p2p_date ("3 din mein clear kar denge",today =TODAY )=="2026-09-01"


def test_extracts_next_week ():
    assert extract_p2p_date ("agle hafte",today =TODAY )=="2026-09-05"


def test_returns_none_when_no_commitment ():
    assert extract_p2p_date ("thik hai dekhta hoon",today =TODAY )is None
    assert extract_p2p_date ("",today =TODAY )is None
