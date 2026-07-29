"""Optional IBKR adapter. The core never imports this package.

    pip install broker-converger[ib]
"""
from .adapter import BrokerReadFailed, IBEvidenceGatherer, read_snapshot
from .contract import NonPaperAccountError, qualified_contract, select_paper_account, tick_round

__all__ = [
    "BrokerReadFailed", "IBEvidenceGatherer", "read_snapshot",
    "NonPaperAccountError", "qualified_contract", "select_paper_account", "tick_round",
]
