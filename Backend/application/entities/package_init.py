"""Model registry that exposes all persistence entities and attaches them to shared metadata."""

from application .entities .audit_record import AuditTrail
from application .entities .call_session import CallSession ,CallTurn
from application .entities .escalation_queue import EscalationQueue
from application .entities .merchant_rules import MerchantPolicy
from application .entities .message_record import Message
from application .entities .handled_event import ProcessedEvent
from application .entities .transaction_record import TransactionState
from application .entities .saved_scenario import SavedScenario

__all__ =[
"AuditTrail",
"CallSession",
"CallTurn",
"EscalationQueue",
"MerchantPolicy",
"Message",
"ProcessedEvent",
"TransactionState",
"SavedScenario",
]
