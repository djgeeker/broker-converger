"""IBKR helpers that are easy to get subtly wrong.

All three divergences noted below were found between two copies inside one
production system.
"""
from __future__ import annotations

from typing import Any


class NonPaperAccountError(RuntimeError):
    """Selected account is not a paper account and the guard is on."""


def tick_round(price: float, tick_size: float) -> float:
    """Snap a price to the instrument's legal increment.

    Non-positive tick raises rather than defaulting: a default puts two parts
    of one system on different price grids, and that produces no error — only
    orders quietly rejected, or quietly accepted at a price you did not intend.

    Rounds to 10 decimals. Two copies of this differed only in that constant
    (10 vs 2). On a 0.25 tick they agree exactly, so it sat there invisibly;
    below 0.01 the 2-decimal version truncates a legal price into an illegal one.
    """
    if not tick_size or tick_size <= 0:
        raise ValueError(f"tick_size must be positive, got {tick_size!r}")
    return round(round(float(price) / tick_size) * tick_size, 10)


def qualified_contract(ib: Any, ContFuture: Any, Future: Any, config: Any) -> Any:
    """Resolve a continuous futures contract into a tradeable expiry.

    ContFuture is a data contract, not something you can send an order for.
    Skipping this resolution is a real incident, not a style point: one leg
    resolved the expiry and another did not, and during a roll week the two
    opened positions in different contracts while every dashboard showed one
    instrument. Re-qualifying before each action also makes rolls explicit
    rather than letting a long-running process trade a dead expiry.

    config needs .connection with contract_type ("contfuture"|"future"),
    symbol, exchange, currency, and month for an explicit future.
    """
    cfg = config.connection
    if cfg.contract_type == "contfuture":
        continuous = ContFuture(cfg.symbol, cfg.exchange, currency=cfg.currency)
        qualified_continuous = ib.qualifyContracts(continuous)
        if not qualified_continuous:
            raise RuntimeError("broker returned no qualified continuous contract")
        expiry = str(getattr(qualified_continuous[0], "lastTradeDateOrContractMonth", "") or "")
        month = expiry[:6]
        if len(month) != 6 or not month.isdigit():
            raise RuntimeError("continuous contract gave no tradeable YYYYMM expiry")
        contract = Future(cfg.symbol, month, cfg.exchange, currency=cfg.currency)
    elif cfg.contract_type == "future":
        if not cfg.month:
            raise ValueError("month is required when contract_type='future'")
        contract = Future(cfg.symbol, cfg.month, cfg.exchange, currency=cfg.currency)
    else:
        raise ValueError(f"unsupported contract_type: {cfg.contract_type}")
    qualified = ib.qualifyContracts(contract)
    if not qualified:
        raise RuntimeError("broker returned no qualified contract")
    return qualified[0]


def select_paper_account(ib: Any, config: Any) -> str:
    """Pick the account to trade and enforce the paper-only guard.

    With several managed accounts and none configured, prefer one matching the
    paper prefix rather than taking the first: both fail closed, but taking the
    first refuses to run whenever the paper account is not listed first.

    The prefix check stays last and unconditional — when on, it is the only
    thing between testing and real money, and an explicitly configured account
    is not exempt.
    """
    accounts = list(ib.managedAccounts() or []) if hasattr(ib, "managedAccounts") else []
    selected = config.account or next(
        (a for a in accounts if a.startswith(config.paper_account_prefix)),
        accounts[0] if accounts else "",
    )
    if config.require_paper_account and not selected.startswith(config.paper_account_prefix):
        raise NonPaperAccountError(f"non_paper_account_rejected:{selected or 'unknown'}")
    return selected
