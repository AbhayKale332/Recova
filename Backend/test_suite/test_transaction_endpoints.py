"""The transactions ledger + audit-log endpoints that feed the dashboard's
Transactions tab, per-class tabs, and Audit Log."""

import pytest

from application .operations .batch_seed import seed_batch


@pytest .fixture ()
def seeded (client ,db_session ):
    seed_batch (db_session )
    return client


def test_list_transactions_returns_ledger (seeded ):
    resp =seeded .get ("/api/v1/transactions")
    assert resp .status_code ==200
    body =resp .json ()
    assert body ["total"]>=40
    assert len (body ["items"])==body ["total"]
    row =body ["items"][0 ]
    for key in ("transaction_id","failure_class","status","amount_inr","ai_tag"):
        assert key in row


def test_list_masks_customer_contact (seeded ):
    body =seeded .get ("/api/v1/transactions").json ()
    for row in body ["items"]:
        masked =row ["customer_contact_masked"]
        assert masked .count ("*")>=4


def test_filter_by_failure_class (seeded ):
    body =seeded .get ("/api/v1/transactions?failure_class=3").json ()
    assert body ["items"]
    assert all (r ["failure_class"]==3 for r in body ["items"])


def test_filter_by_status (seeded ):
    body =seeded .get ("/api/v1/transactions?status=RECOVERED").json ()
    assert body ["items"]
    assert all (r ["status"]=="RECOVERED"for r in body ["items"])


def test_search_by_customer_or_id (seeded ):
    first =seeded .get ("/api/v1/transactions").json ()["items"][0 ]
    tid =first ["transaction_id"]
    body =seeded .get (f"/api/v1/transactions?q={tid [-6 :]}").json ()
    assert any (r ["transaction_id"]==tid for r in body ["items"])


def test_recovery_case_carries_derived_playbook_and_channel (seeded ):
    body =seeded .get ("/api/v1/transactions?failure_class=2&status=RECOVERED").json ()
    assert body ["items"]
    row =body ["items"][0 ]
    assert row ["playbook"]
    assert row ["channel"]


def test_transaction_detail_includes_audit_and_diagnosis (seeded ):
    tid =seeded .get (
    "/api/v1/transactions?failure_class=2&status=RECOVERED"
    ).json ()["items"][0 ]["transaction_id"]
    resp =seeded .get (f"/api/v1/transactions/{tid }")
    assert resp .status_code ==200
    detail =resp .json ()
    assert detail ["transaction_id"]==tid
    assert len (detail ["audit_trail"])>=2
    assert detail ["diagnosis"]["root_cause"]
    assert detail ["diagnosis"]["recommended_playbook"]


def test_transaction_detail_404_for_unknown (seeded ):
    assert seeded .get ("/api/v1/transactions/nope").status_code ==404


def test_audit_log_endpoint (seeded ):
    resp =seeded .get ("/api/v1/audit")
    assert resp .status_code ==200
    body =resp .json ()
    assert body ["total"]>=1
    entry =body ["items"][0 ]
    for key in ("transaction_id","node_name","action_type","outcome","timestamp"):
        assert key in entry


def test_audit_log_filter_by_transaction (seeded ):
    tid =seeded .get (
    "/api/v1/transactions?failure_class=2&status=RECOVERED"
    ).json ()["items"][0 ]["transaction_id"]
    body =seeded .get (f"/api/v1/audit?transaction_id={tid }").json ()
    assert body ["items"]
    assert all (e ["transaction_id"]==tid for e in body ["items"])
