"""broker-converger — desired-state convergence for broker orders.

Three rules, each made structural rather than documented:

1. Read before act — cannot read, do nothing this cycle.
2. One corrective per cycle — plan() returns Optional[Correction].
3. Never trust the echo — order state is whatever the next snapshot says.

    from broker_converger import DesiredOrder, DesiredState, plan

    snapshot = read_the_broker()               # raise if it fails
    desired  = my_strategy_to_desired_state()  # the only function you write
    action   = plan(desired=desired, snapshot=snapshot, price_tick=0.25)
    if action is not None:
        actuators[action.kind](action)         # your order code
"""
from .desired import DesiredOrder, DesiredState
from .fills import AggregatedFills, aggregate
from .ladder import Correction, find_order, plan
from .outbox import ExecutionOutbox
from .ownership import owned_exit_quantity, quantity_on_contract
from .snapshot import BrokerOrderView, BrokerSnapshot
from .verification import (
    Evidence, SubmissionRecord, Verdict, due_for_verification, rule, verify,
)

__version__ = "0.1.0"

__all__ = [
    "BrokerOrderView", "BrokerSnapshot",
    "DesiredOrder", "DesiredState",
    "Correction", "plan", "find_order",
    "owned_exit_quantity", "quantity_on_contract",
    "AggregatedFills", "aggregate",
    "ExecutionOutbox",
    "SubmissionRecord", "Evidence", "Verdict",
    "due_for_verification", "rule", "verify",
]
