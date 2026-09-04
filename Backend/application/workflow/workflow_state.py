"""Typed state contract passed between recovery workflow nodes."""

from datetime import datetime
from typing import Any ,Optional ,TypedDict


class RecoveryState (TypedDict ,total =False ):
    transaction_id :str
    failure_class :int
    telemetry :dict [str ,Any ]
    user_message :Optional [str ]

    lifecycle :str
    playbook :Optional [str ]
    root_cause :Optional [str ]
    retry_count :int

    proposed_discount_pct :Optional [float ]

    voice_attempts :int

    # IST wall clock the compliance gates are evaluated against. Injected rather
    # than read from the system clock so a simulated scenario can ask what the
    # engine would do at 21:40, and so tests are not time-of-day dependent.
    now_ist :Optional [datetime ]


    outcome_event :Optional [str ]


    disposition :Optional [str ]
    stopping_rule :Optional [str ]
