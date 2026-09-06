"""POST /admin/seed truncates every table, so it must never be openly reachable.

The gate fails closed: an unset ADMIN_TOKEN disables the route rather than
leaving it public, which is what a deployment that forgets the variable needs.
"""

import pytest

from application .settings import settings


@pytest .fixture ()
def admin_token ():
    """Configure a token for the duration of one test, then restore."""
    original =settings .admin_token
    settings .admin_token ="test-admin-token"
    try :
        yield settings .admin_token
    finally :
        settings .admin_token =original


@pytest .fixture ()
def no_admin_token ():
    original =settings .admin_token
    settings .admin_token =""
    try :
        yield
    finally :
        settings .admin_token =original


def test_seed_is_disabled_when_no_token_is_configured (client ,no_admin_token ):
    response =client .post ("/api/v1/admin/seed")

    assert response .status_code ==404
    assert "ADMIN_TOKEN"in response .json ()["detail"]


def test_seed_rejects_a_missing_header (client ,admin_token ):
    response =client .post ("/api/v1/admin/seed")

    assert response .status_code ==401


def test_seed_rejects_a_wrong_token (client ,admin_token ):
    response =client .post (
    "/api/v1/admin/seed",
    headers ={"X-Admin-Token":"not-the-token"},
    )

    assert response .status_code ==401


def test_seed_rejects_a_token_that_is_a_prefix_of_the_real_one (client ,admin_token ):
    response =client .post (
    "/api/v1/admin/seed",
    headers ={"X-Admin-Token":admin_token [:-1 ]},
    )

    assert response .status_code ==401


def test_seed_runs_with_the_correct_token (client ,admin_token ):
    response =client .post (
    "/api/v1/admin/seed",
    headers ={"X-Admin-Token":admin_token },
    )

    assert response .status_code ==200
    body =response .json ()
    assert body ["seeded"]>0
    assert body ["by_state"]
