from application .constants import InterventionAction ,InterventionChannel
from application .operations .policy_guard import PolicySandbox ,ProposedAction


POLICY ={
"max_discount_pct":15 ,
"max_intervention_amount_minor":1_000_000 ,
"allowed_channels":["WHATSAPP","VOICE","PAYMENT_LINK"],
"allowed_actions":[
"SEND_WHATSAPP",
"VOICE_CALL",
"OFFER_FEE_WAIVER",
"GENERATE_PAYMENT_LINK",
"RETRY_CHARGE",
"CANCEL_SUBSCRIPTION",
],
}


def _sandbox ():
    return PolicySandbox (POLICY )


def test_allows_a_compliant_whatsapp_nudge ():
    action =ProposedAction (
    action =InterventionAction .SEND_WHATSAPP ,
    channel =InterventionChannel .WHATSAPP ,
    )
    decision =_sandbox ().validate (action )
    assert decision .approved is True


def test_blocks_discount_above_cap ():

    action =ProposedAction (
    action =InterventionAction .OFFER_FEE_WAIVER ,
    channel =InterventionChannel .WHATSAPP ,
    discount_pct =50 ,
    )
    decision =_sandbox ().validate (action )
    assert decision .approved is False
    assert "discount"in decision .reason .lower ()


def test_blocks_disallowed_channel ():
    action =ProposedAction (
    action =InterventionAction .SEND_WHATSAPP ,
    channel ="SMS",
    )
    decision =_sandbox ().validate (action )
    assert decision .approved is False


def test_blocks_amount_above_ceiling ():
    action =ProposedAction (
    action =InterventionAction .GENERATE_PAYMENT_LINK ,
    channel =InterventionChannel .PAYMENT_LINK ,
    amount_minor =5_000_000 ,
    )
    decision =_sandbox ().validate (action )
    assert decision .approved is False


def test_amount_ceiling_message_is_rupees_not_paise ():
    # The theatre renders this sentence verbatim (DecisionCard); it must read
    # ₹48,000, not the raw paise figure 4800000.
    action =ProposedAction (
    action =InterventionAction .GENERATE_PAYMENT_LINK ,
    channel =InterventionChannel .PAYMENT_LINK ,
    amount_minor =4_800_000 ,
    )
    decision =_sandbox ().validate (action )
    assert decision .approved is False
    assert decision .reason =="Amount ₹48,000 exceeds the ₹10,000 policy ceiling."
    assert "4800000"not in decision .reason
    assert "1000000"not in decision .reason


def test_amount_ceiling_ignores_non_money_actions ():



    nudge =ProposedAction (
    action =InterventionAction .SEND_WHATSAPP ,
    channel =InterventionChannel .WHATSAPP ,
    amount_minor =8_400_000 ,
    )
    assert _sandbox ().validate (nudge ).approved is True


def test_amount_ceiling_still_blocks_a_large_charge ():
    charge =ProposedAction (
    action =InterventionAction .RETRY_CHARGE ,
    amount_minor =8_400_000 ,
    )
    assert _sandbox ().validate (charge ).approved is False


def test_prompt_injection_cannot_elevate_a_full_waiver ():


    action =ProposedAction (
    action =InterventionAction .OFFER_FEE_WAIVER ,
    channel =InterventionChannel .WHATSAPP ,
    discount_pct =100 ,
    )
    assert _sandbox ().validate (action ).approved is False


def test_default_sandbox_loads_shipped_policy_file ():

    sandbox =PolicySandbox .from_default_policy ()
    action =ProposedAction (
    action =InterventionAction .SEND_WHATSAPP ,
    channel =InterventionChannel .WHATSAPP ,
    )
    assert sandbox .validate (action ).approved is True
