from application .operations .idempotency_service import claim_event


def test_first_claim_succeeds (db_session ):
    assert claim_event (db_session ,"evt_abc")is True


def test_duplicate_claim_is_rejected (db_session ):
    assert claim_event (db_session ,"evt_dup")is True

    assert claim_event (db_session ,"evt_dup")is False


def test_distinct_ids_are_independent (db_session ):
    assert claim_event (db_session ,"evt_1")is True
    assert claim_event (db_session ,"evt_2")is True
