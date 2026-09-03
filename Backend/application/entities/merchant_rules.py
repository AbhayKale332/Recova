"""Persistence model for the single operator-editable merchant policy."""

from sqlalchemy import JSON ,Column ,Integer

from application .persistence import Base


class MerchantPolicy (Base ):
    """The operator-editable compliance policy (a single row).

    The deterministic PolicySandbox is built from this, so tuning the ceiling or
    discount cap here actually changes what the automated recovery process is allowed to do. Only a human
    operator edits it — the conversational layer has no path to write here, which
    is exactly what keeps the guardrails un-negotiable by the model.
    """

    __tablename__ ="merchant_policy"

    id =Column (Integer ,primary_key =True )
    max_discount_pct =Column (Integer ,nullable =False )
    max_intervention_amount_minor =Column (Integer ,nullable =False )
    allowed_actions =Column (JSON ,nullable =False )
    allowed_channels =Column (JSON ,nullable =False )

    def as_dict (self )->dict :
        return {
        "max_discount_pct":self .max_discount_pct ,
        "max_intervention_amount_minor":self .max_intervention_amount_minor ,
        "allowed_actions":list (self .allowed_actions or []),
        "allowed_channels":list (self .allowed_channels or []),
        }
