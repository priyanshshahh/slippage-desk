"""Thin wrappers around the Alpaca SDK clients.

Everything that touches the network goes through here so the rest of the
engine stays testable and the credential surface stays small.
"""
from __future__ import annotations

from functools import lru_cache

from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.trading.client import TradingClient

from engine.config import Credentials


@lru_cache(maxsize=1)
def _creds() -> Credentials:
    return Credentials.from_env()


@lru_cache(maxsize=1)
def trading() -> TradingClient:
    c = _creds()
    return TradingClient(c.api_key, c.secret_key, paper=c.paper)


@lru_cache(maxsize=1)
def option_data() -> OptionHistoricalDataClient:
    c = _creds()
    return OptionHistoricalDataClient(c.api_key, c.secret_key)


@lru_cache(maxsize=1)
def stock_data() -> StockHistoricalDataClient:
    c = _creds()
    return StockHistoricalDataClient(c.api_key, c.secret_key)


def options_feed() -> str:
    return _creds().options_feed
