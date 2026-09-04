"""Neutral mappings shared by diagnosis, workflow, simulation, and tools.

Keeping these translations in ``operations`` prevents the operations package
from importing workflow implementation details.
"""

from application.constants import FailureClass, InterventionAction, InterventionChannel, Playbook


PLAYBOOK_ACTION: dict[Playbook, tuple[InterventionAction, InterventionChannel | None]] = {
    Playbook.REROUTE_RAIL: (InterventionAction.GENERATE_PAYMENT_LINK, InterventionChannel.PAYMENT_LINK),
    Playbook.PREAUTH_LINK: (InterventionAction.GENERATE_PAYMENT_LINK, InterventionChannel.PAYMENT_LINK),
    Playbook.UPI_AUTOPAY_NUDGE: (InterventionAction.SEND_WHATSAPP, InterventionChannel.WHATSAPP),
    Playbook.NEGOTIATION: (InterventionAction.OFFER_FEE_WAIVER, InterventionChannel.WHATSAPP),
    Playbook.SALARY_CYCLE_SEQUENCER: (InterventionAction.RETRY_CHARGE, None),
    Playbook.MANDATE_REFRESH: (InterventionAction.VOICE_CALL, InterventionChannel.VOICE),
    Playbook.P2P_TRACKER: (InterventionAction.SEND_WHATSAPP, InterventionChannel.WHATSAPP),
}


DEFAULT_PLAYBOOK: dict[FailureClass, Playbook] = {
    FailureClass.REALTIME_DEGRADATION: Playbook.REROUTE_RAIL,
    FailureClass.CHECKOUT_ABANDONMENT: Playbook.UPI_AUTOPAY_NUDGE,
    FailureClass.SUBSCRIPTION_MANDATE: Playbook.SALARY_CYCLE_SEQUENCER,
    FailureClass.B2B_RECEIVABLES: Playbook.P2P_TRACKER,
}
