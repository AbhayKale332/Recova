"""Common result contract returned by channel and payment adapters."""

from dataclasses import dataclass


@dataclass
class DispatchResult :
    channel :str
    delivered :bool
    simulated :bool
    reference :str |None =None
    detail :str |None =None
    url :str |None =None
    image_url :str |None =None
