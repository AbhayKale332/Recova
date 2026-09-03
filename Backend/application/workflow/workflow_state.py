"""Typed state contract passed between recovery workflow nodes."""

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


    outcome_event :Optional [str ]


    disposition :Optional [str ]
    stopping_rule :Optional [str ]
