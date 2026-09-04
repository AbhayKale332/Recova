"""Outcome probability model for the recovery simulator.

Why a model at all: the simulator reports two different numbers and they must not
be confused. *Recovered* is measured - the rupee value of cases the engine
actually drove to RECOVERED in this run. *Projected* is modelled - the expected
value across the whole book, with a band. This module owns the second one.

Why priors rather than a fitted model: the only labelled outcomes in the database
were written by ``batch_seed.py``, so a model trained on them would re-learn the
seeder's own constants and report that as evidence. Instead each stratum starts
from a Beta prior whose reasoning is written down beside it, and the posterior
sharpens from real completed cases as the system is used.

Closed form and pure stdlib on purpose - it runs per case inside the worker pool,
and the project has no numeric dependency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass ,field

from application .constants import FailureClass ,InterventionChannel ,Playbook

# One standard normal quantile for a 95% interval.
_Z95 =1.959964


def _sigmoid (x :float )->float :
    # Guard the exponential so an extreme logit cannot overflow.
    if x >=0 :
        return 1.0 /(1.0 +math .exp (-min (x ,60.0 )))
    e =math .exp (max (x ,-60.0 ))
    return e /(1.0 +e )


def _logit (p :float )->float :
    p =min (max (p ,1e-6 ),1.0 -1e-6 )
    return math .log (p /(1.0 -p ))


@dataclass
class Beta :
    """A Beta(alpha, beta) belief about one stratum's pay-through rate.

    ``alpha`` and ``beta`` read as pseudo-counts: Beta(7, 3) is "as if we had
    seen 7 payments in 10 attempts". They are kept deliberately small so a
    handful of real outcomes can move the estimate.
    """

    alpha :float
    beta :float

    @property
    def mean (self )->float :
        return self .alpha /(self .alpha +self .beta )

    @property
    def variance (self )->float :
        n =self .alpha +self .beta
        return (self .alpha *self .beta )/(n *n *(n +1.0 ))

    def updated (self ,successes :int ,failures :int )->"Beta":
        return Beta (self .alpha +successes ,self .beta +failures )


# Priors per (failure class, playbook, channel). The rationale matters more than
# the exact number: these are starting beliefs a domain expert would defend, and
# every one of them is displaced by observed outcomes.
#
#   Class 1  a rail problem is ours, not the customer's - retrying over a healthy
#            rail succeeds often, so the prior is high and fairly confident.
#   Class 2  the customer already wanted to buy and stalled on 3DS friction; a
#            1-tap link removes the thing that stopped them.
#   Class 3  a balance problem, not an intent problem. Retrying at random fails;
#            retrying inside the salary window is the whole insight, so the
#            sequencer's prior sits well above a bare mandate refresh.
#   Class 4  a business decision on someone else's payment run. A promise-to-pay
#            is realistic; converting it inside the window, less so.
_PRIORS :dict [tuple [int ,str ,str |None ],Beta ]={
(1 ,Playbook .REROUTE_RAIL .value ,InterventionChannel .PAYMENT_LINK .value ):Beta (7.0 ,3.0 ),
(1 ,Playbook .PREAUTH_LINK .value ,InterventionChannel .PAYMENT_LINK .value ):Beta (6.0 ,4.0 ),
(2 ,Playbook .UPI_AUTOPAY_NUDGE .value ,InterventionChannel .WHATSAPP .value ):Beta (5.5 ,4.5 ),
(2 ,Playbook .PREAUTH_LINK .value ,InterventionChannel .PAYMENT_LINK .value ):Beta (5.0 ,5.0 ),
(3 ,Playbook .SALARY_CYCLE_SEQUENCER .value ,None ):Beta (6.5 ,3.5 ),
(3 ,Playbook .MANDATE_REFRESH .value ,InterventionChannel .VOICE .value ):Beta (4.0 ,6.0 ),
(4 ,Playbook .P2P_TRACKER .value ,InterventionChannel .WHATSAPP .value ):Beta (4.5 ,5.5 ),
(4 ,Playbook .NEGOTIATION .value ,InterventionChannel .WHATSAPP .value ):Beta (5.0 ,5.0 ),
}

# Used when a class/playbook/channel combination has no prior of its own. Wide on
# purpose: an unmodelled path should widen the band, not quietly borrow
# confidence from a neighbouring stratum.
_FALLBACK_PRIOR =Beta (2.0 ,3.0 )

# Log-odds adjustments applied on top of the stratum's rate. Signs are the claim;
# magnitudes are calibrated so no single feature can dominate the prior.
_COEFFICIENTS ={
# Bigger asks convert worse. Measured per natural-log step above a
# ~5,000 rupee reference, so 50,000 costs about one step.
"amount":-0.18 ,
# The message cannot go out tonight. Deferred contact is not lost contact,
# but it is a day of decay.
"quiet_hours":-0.55 ,
# Each retry already spent is evidence the easy path failed, and it consumes
# the RBI budget that would have paid for another try.
"retries_used":-0.45 ,
# Receivables age badly: about a third of the odds gone by 90 days.
"days_overdue":-0.006 ,
# We already tried this channel and they did not act on it.
"channel_retried":-0.50 ,
}

_AMOUNT_REFERENCE_INR =5000.0


@dataclass
class Contribution :
    """One feature's effect on this case, in percentage points."""

    feature :str
    detail :str
    delta_pp :float


@dataclass
class CaseProbability :
    p :float
    base_rate :float
    variance :float
    contributions :list [Contribution ]=field (default_factory =list )


@dataclass
class CaseFeatures :
    """Everything the model reads about one case."""

    failure_class :int
    playbook :str
    channel :str |None
    amount_inr :float
    in_quiet_hours :bool =False
    retries_used :int =0
    days_overdue :int =0
    channel_retried :bool =False
    # A bound the engine has already hit. Not a penalty - the case will not be
    # worked at all, so no amount of favourable features can recover it.
    blocked_by :str |None =None


def prior_for (failure_class :int ,playbook :str ,channel :str |None )->Beta :
    return _PRIORS .get ((int (failure_class ),playbook ,channel ),_FALLBACK_PRIOR )


def _terms (f :CaseFeatures )->list [tuple [str ,str ,float ]]:
    """(feature, human detail, log-odds shift) for every active adjustment."""
    out :list [tuple [str ,str ,float ]]=[]

    steps =math .log (max (f .amount_inr ,1.0 )/_AMOUNT_REFERENCE_INR )
    if abs (steps )>1e-9 :
        out .append (("amount",f"₹{f .amount_inr :,.0f}",_COEFFICIENTS ["amount"]*steps ))

    if f .in_quiet_hours :
        out .append (("quiet_hours","contact deferred to 09:00 IST",_COEFFICIENTS ["quiet_hours"]))

    if f .retries_used :
        out .append ((
        "retries_used",
        f"{f .retries_used } retry attempt(s) already used",
        _COEFFICIENTS ["retries_used"]*f .retries_used ,
        ))

    if f .days_overdue :
        out .append ((
        "days_overdue",
        f"{f .days_overdue } days overdue",
        _COEFFICIENTS ["days_overdue"]*f .days_overdue ,
        ))

    if f .channel_retried :
        out .append (("channel_retried","this channel was already tried",_COEFFICIENTS ["channel_retried"]))

    return out


def estimate (f :CaseFeatures ,prior :Beta |None =None )->CaseProbability :
    """Probability this case pays, with a per-feature explanation.

    Contributions are leave-one-out: each is the percentage-point difference
    between the full estimate and the estimate with that one feature removed.
    They will not sum exactly to ``p - base_rate`` because the logistic link is
    not additive in probability space - they rank and size the drivers, they are
    not an exact decomposition.
    """
    belief =prior or prior_for (f .failure_class ,f .playbook ,f .channel )
    base =belief .mean

    # A bound is not a headwind, it is a wall. The engine refuses to act, so the
    # projection has to read zero rather than a merely-reduced number - otherwise
    # it would forecast recovery from cases it is about to stop itself.
    if f .blocked_by :
        return CaseProbability (
        p =0.0 ,
        base_rate =base ,
        variance =0.0 ,
        contributions =[
        Contribution (
        feature ="blocked",
        detail =f"{f .blocked_by } — the engine will not work this case",
        delta_pp =round (-base *100 ,2 ),
        )
        ],
        )

    base_logit =_logit (base )

    terms =_terms (f )
    total =sum (shift for _ ,_ ,shift in terms )
    p =_sigmoid (base_logit +total )

    contributions =[
    Contribution (
    feature =name ,
    detail =detail ,
    delta_pp =round ((p -_sigmoid (base_logit +total -shift ))*100 ,2 ),
    )
    for name ,detail ,shift in terms
    ]
    contributions .sort (key =lambda c :abs (c .delta_pp ),reverse =True )

    # Delta method: carry the prior's uncertainty through the logistic shift.
    slope =(p *(1 -p ))/max (base *(1 -base ),1e-9 )
    variance =belief .variance *slope *slope

    return CaseProbability (
    p =p ,
    base_rate =base ,
    variance =variance ,
    contributions =contributions ,
    )


@dataclass
class Projection:
    """Expected recovery across a book of cases, in rupees."""

    expected_inr :float
    low_inr :float
    high_inr :float
    expected_cases :float


def project (cases :list [tuple [CaseProbability ,float ]])->Projection :
    """Aggregate per-case probabilities into a projection with a 95% band.

    ``cases`` is (probability, amount_inr) pairs. The variance carries two
    distinct sources of doubt and needs both: outcome randomness (a case with
    p=0.6 either pays or does not) and parameter uncertainty (we are not certain
    p is 0.6). Reporting only the first would understate the band, which is the
    kind of false precision this whole screen exists to avoid.
    """
    if not cases :
        return Projection (0.0 ,0.0 ,0.0 ,0.0 )

    mean =sum (cp .p *amount for cp ,amount in cases )
    variance =sum (
    (cp .p *(1 -cp .p )+cp .variance )*amount *amount for cp ,amount in cases
    )
    spread =_Z95 *math .sqrt (variance )
    total =sum (amount for _ ,amount in cases )

    return Projection (
    expected_inr =round (mean ,2 ),
    low_inr =round (max (0.0 ,mean -spread ),2 ),
    high_inr =round (min (total ,mean +spread ),2 ),
    expected_cases =round (sum (cp .p for cp ,_ in cases ),2 ),
    )


def observed_posteriors (rows :list [tuple [int ,str ,str |None ,bool ]])->dict [tuple ,Beta ]:
    """Fold real outcomes into the priors.

    ``rows`` is (failure_class, playbook, channel, recovered) for completed,
    non-simulated cases. This is what makes the module a model rather than a
    lookup table: the more the engine actually runs, the less the hand-set prior
    matters.
    """
    tallies :dict [tuple ,list [int ]]={}
    for failure_class ,playbook ,channel ,recovered in rows :
        key =(int (failure_class ),playbook ,channel )
        tally =tallies .setdefault (key ,[0 ,0 ])
        tally [0 if recovered else 1 ]+=1

    return {
    key :prior_for (*key ).updated (successes ,failures )
    for key ,(successes ,failures )in tallies .items ()
    }


def features_for_class (failure_class :int )->tuple [str ,str |None ]:
    """The playbook and channel the engine would pick for a class by default.

    Mirrors ``DEFAULT_PLAYBOOK`` and ``PLAYBOOK_ACTION`` in the neutral operations
    map, so a projection made before a run predicts the same path the
    run will actually take.
    """
    from application .operations .playbook_map import DEFAULT_PLAYBOOK, PLAYBOOK_ACTION

    playbook =DEFAULT_PLAYBOOK [FailureClass (failure_class )]
    _action ,channel =PLAYBOOK_ACTION [playbook ]
    return playbook .value ,(channel .value if channel else None )
