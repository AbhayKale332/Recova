"""The read-only policy endpoint behind the dashboard's Policy Inspector — it
surfaces the deterministic 'Bouncer' the sandbox enforces."""


def test_policy_endpoint_exposes_merchant_policy (client ):
    resp =client .get ("/api/v1/policy")
    assert resp .status_code ==200
    body =resp .json ()
    policy =body ["policy"]
    assert policy ["max_intervention_amount_minor"]==1000000
    assert policy ["max_discount_pct"]==15
    assert "WHATSAPP"in policy ["allowed_channels"]


def test_policy_endpoint_lists_money_moving_actions (client ):
    body =client .get ("/api/v1/policy").json ()
    assert "GENERATE_PAYMENT_LINK"in body ["money_moving_actions"]

    assert "SEND_WHATSAPP"not in body ["money_moving_actions"]


def test_policy_endpoint_lists_stopping_rules (client ):
    body =client .get ("/api/v1/policy").json ()
    rules ={r ["name"]:r ["description"]for r in body ["stopping_rules"]}
    assert "RBI_MAX_RETRIES"in rules
    assert "TRAI_QUIET_HOURS"in rules
    assert rules ["RBI_MAX_RETRIES"]
