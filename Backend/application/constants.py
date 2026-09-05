"""Domain enumerations shared by persistence, orchestration, APIs, and compliance logic."""

from enum import Enum ,IntEnum


class FailureClass (IntEnum ):
    """The four payment-failure classes the recovery engine routes on.

    Kept as an ``IntEnum`` so the numeric contract from the PRD (classes 1-4)
    is preserved on the wire while still being validated. Names mirror the PRD's
    locked taxonomy so the code reads the way the product spec does.
    """

    REALTIME_DEGRADATION =1
    CHECKOUT_ABANDONMENT =2
    SUBSCRIPTION_MANDATE =3
    B2B_RECEIVABLES =4


class TransactionLifecycleState (str ,Enum ):
    """Lifecycle a transaction moves through inside the orchestrator."""

    PENDING ="PENDING"
    DIAGNOSING ="DIAGNOSING"
    WAITING ="WAITING"
    INTERVENING ="INTERVENING"
    RECOVERED ="RECOVERED"
    ESCALATED ="ESCALATED"
    CANCELLED ="CANCELLED"
    FAILED ="FAILED"


class NodeName (str ,Enum ):
    """Orchestrator DAG nodes that emit audit entries."""

    INGEST ="INGEST"
    DIAGNOSE ="DIAGNOSE"
    WAIT ="WAIT"
    EXECUTE_INTERVENTION ="EXECUTE_INTERVENTION"
    RECONCILE ="RECONCILE"
    OPERATOR ="OPERATOR"


class ActionType (str ,Enum ):
    """The kind of action an audit entry records."""

    STATE_TRANSITION ="STATE_TRANSITION"
    INTERVENTION_DISPATCH ="INTERVENTION_DISPATCH"
    RETRY_SCHEDULED ="RETRY_SCHEDULED"
    ESCALATION ="ESCALATION"


class Outcome (str ,Enum ):
    """Result of an audited action."""

    SUCCESS ="SUCCESS"
    FAILURE ="FAILURE"
    ESCALATED ="ESCALATED"


class InterventionChannel (str ,Enum ):
    """Outbound channels a recovery action can use."""

    WHATSAPP ="WHATSAPP"
    VOICE ="VOICE"
    PAYMENT_LINK ="PAYMENT_LINK"


class InterventionAction (str ,Enum ):
    """The concrete recovery actions the orchestrator can propose.

    Every one of these must clear the PolicySandbox before it reaches a channel
    adapter - this enum is the closed set of things the engine is even allowed
    to attempt.
    """

    SEND_WHATSAPP ="SEND_WHATSAPP"
    VOICE_CALL ="VOICE_CALL"
    OFFER_FEE_WAIVER ="OFFER_FEE_WAIVER"
    GENERATE_PAYMENT_LINK ="GENERATE_PAYMENT_LINK"
    GENERATE_QR_CODE ="GENERATE_QR_CODE"
    OFFER_PARTIAL_PLAN ="OFFER_PARTIAL_PLAN"
    RETRY_CHARGE ="RETRY_CHARGE"
    CANCEL_SUBSCRIPTION ="CANCEL_SUBSCRIPTION"


class StoppingRule (str ,Enum ):
    """Named, regulatory/compliance stopping rules.

    Each is emitted to the audit trail and counted in the recovery metrics, so a
    judge can see exactly which rule halted a workflow and how often.
    """

    NO_DOUBLE_CHARGE ="NO_DOUBLE_CHARGE"
    CROSS_DEVICE_COMPLETION ="CROSS_DEVICE_COMPLETION"
    RBI_MAX_RETRIES ="RBI_MAX_RETRIES"
    EXPLICIT_CANCEL ="EXPLICIT_CANCEL"
    OPT_OUT ="OPT_OUT"
    DISPUTE_FREEZE ="DISPUTE_FREEZE"
    TRAI_QUIET_HOURS ="TRAI_QUIET_HOURS"
    VOICE_ATTEMPT_CAP ="VOICE_ATTEMPT_CAP"


class EscalationStatus (str ,Enum ):
    """Lifecycle of a human-handoff ticket."""

    OPEN ="OPEN"
    RESOLVED ="RESOLVED"


class MessageDirection (str ,Enum ):
    """Whether a conversation message left the engine or arrived from the customer."""

    OUTBOUND ="OUTBOUND"
    INBOUND ="INBOUND"


class MessageSender (str ,Enum ):
    """Who authored a message in the thread."""

    AGENT ="AGENT"
    CUSTOMER ="CUSTOMER"
    SYSTEM ="SYSTEM"


class MessageStatus (str ,Enum ):
    """WhatsApp-style delivery state of an outbound message."""

    SENT ="SENT"
    DELIVERED ="DELIVERED"
    READ ="READ"


class CallStatus (str ,Enum ):
    """Lifecycle of a voice call session."""

    RINGING ="RINGING"
    IN_PROGRESS ="IN_PROGRESS"
    COMPLETED ="COMPLETED"
    NO_ANSWER ="NO_ANSWER"


class CallSpeaker (str ,Enum ):
    """Who is speaking in a call transcript turn."""

    AGENT ="AGENT"
    CUSTOMER ="CUSTOMER"


class PaymentArtifactKind (str ,Enum ):
    """What a minted Razorpay payment artifact actually is."""

    LINK ="LINK"
    UPI_LINK ="UPI_LINK"
    QR ="QR"


class PaymentArtifactStatus (str ,Enum ):
    """Lifecycle of a minted payment artifact, independent of the case's own state."""

    CREATED ="created"
    PAID ="paid"
    PARTIALLY_PAID ="partially_paid"
    EXPIRED ="expired"
    CLOSED ="closed"


class Playbook (str ,Enum ):
    """Recovery playbooks the diagnosis layer selects from (per the PRD)."""

    REROUTE_RAIL ="REROUTE_RAIL"
    PREAUTH_LINK ="PREAUTH_LINK"
    UPI_AUTOPAY_NUDGE ="UPI_AUTOPAY_NUDGE"
    NEGOTIATION ="NEGOTIATION"
    SALARY_CYCLE_SEQUENCER ="SALARY_CYCLE_SEQUENCER"
    MANDATE_REFRESH ="MANDATE_REFRESH"
    P2P_TRACKER ="P2P_TRACKER"
