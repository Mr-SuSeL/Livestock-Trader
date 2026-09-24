"""
Experimental Yahoo Finance futures-options probe.

Purpose:
    - test whether Yahoo exposes options for futures contracts
    - inspect available expirations
    - inspect raw calls/puts schemas
    - do NOT calculate Greeks, GEX or VEX yet

Yahoo is treated as a research/fallback source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf


SOURCE_NAME = "YAHOO"


class YahooOptionsError(RuntimeError):
    """Base exception for Yahoo options collector errors."""


class YahooOptionsUnavailable(YahooOptionsError):
    """Raised when no options are available for a symbol."""


@dataclass(frozen=True, slots=True)
class YahooOptionChain:
    symbol: str
    expiration: str
    calls: pd.DataFrame
    puts: pd.DataFrame
    retrieved_at: datetime
    source: str = SOURCE_NAME


def normalize_symbol(symbol: str) -> str:
    """Normalize Yahoo provider symbol."""

    normalized = symbol.strip().upper()

    if not normalized:
        raise ValueError(
            "Yahoo options symbol cannot be empty."
        )

    return normalized


def get_expirations(symbol: str) -> tuple[str, ...]:
    """
    Return all option expirations exposed by Yahoo.
    """

    normalized = normalize_symbol(symbol)

    try:
        ticker = yf.Ticker(normalized)
        expirations = ticker.options

    except Exception as exc:
        raise YahooOptionsError(
            f"Yahoo options request failed "
            f"for {normalized}: {exc}"
        ) from exc

    if not expirations:
        raise YahooOptionsUnavailable(
            f"No option expirations returned "
            f"for {normalized}."
        )

    return tuple(expirations)


def collect_option_chain(
    symbol: str,
    expiration: str,
) -> YahooOptionChain:
    """
    Retrieve one raw option chain.

    No normalization is intentionally performed yet.
    """

    normalized = normalize_symbol(symbol)

    try:
        ticker = yf.Ticker(normalized)

        chain = ticker.option_chain(
            expiration
        )

    except Exception as exc:
        raise YahooOptionsError(
            f"Yahoo option-chain request failed "
            f"for {normalized} / {expiration}: "
            f"{exc}"
        ) from exc

    calls = chain.calls.copy()
    puts = chain.puts.copy()

    if calls.empty and puts.empty:
        raise YahooOptionsUnavailable(
            f"Empty option chain for "
            f"{normalized} / {expiration}."
        )

    return YahooOptionChain(
        symbol=normalized,
        expiration=expiration,
        calls=calls,
        puts=puts,
        retrieved_at=datetime.now(
            timezone.utc
        ),
    )


def _print_dataframe_info(
    title: str,
    dataframe: pd.DataFrame,
) -> None:
    """Print schema and a small sample."""

    print()
    print(title)
    print("-" * 70)

    print(f"Rows: {len(dataframe):,}")

    print(
        "Columns: "
        + ", ".join(
            str(column)
            for column in dataframe.columns
        )
    )

    if dataframe.empty:
        print("EMPTY")
        return

    print()
    print(
        dataframe.head(5).to_string(
            index=False
        )
    )


def probe(symbol: str) -> bool:
    """
    Probe Yahoo futures-options availability.
    """

    normalized = normalize_symbol(symbol)

    print("=" * 70)
    print("YAHOO FUTURES OPTIONS PROBE")
    print("=" * 70)

    print(f"Source: {SOURCE_NAME}")
    print(f"Symbol: {normalized}")
    print()

    try:
        expirations = get_expirations(
            normalized
        )

    except YahooOptionsError as exc:
        print("Status: FAILED")
        print(f"Reason: {exc}")
        return False

    print("Status: EXPIRATIONS_FOUND")
    print(
        f"Expiration count: "
        f"{len(expirations)}"
    )

    for expiration in expirations:
        print(f"  {expiration}")

    # Probe only the nearest expiration first.
    expiration = expirations[0]

    print()
    print(
        f"Testing expiration: {expiration}"
    )

    try:
        chain = collect_option_chain(
            symbol=normalized,
            expiration=expiration,
        )

    except YahooOptionsError as exc:
        print("Status: CHAIN_FAILED")
        print(f"Reason: {exc}")
        return False

    print()
    print("Status: CHAIN_OK")

    _print_dataframe_info(
        "CALLS",
        chain.calls,
    )

    _print_dataframe_info(
        "PUTS",
        chain.puts,
    )

    print()
    print(
        f"Retrieved at: "
        f"{chain.retrieved_at.isoformat()}"
    )

    return True


def main() -> None:
    """
    Run experimental Lean Hogs probes.

    Symbols are explicit here because this file currently serves
    as a provider capability diagnostic.
    """

    symbols = (
        "HEV26.CME",
        "HEZ26.CME",
    )

    for symbol in symbols:

        print()
        probe(symbol)
        print()


if __name__ == "__main__":
    main()