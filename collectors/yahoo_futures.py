"""
Generic Yahoo Finance market-data collector.

The collector is instrument-agnostic.

It receives a Yahoo Finance symbol from the caller and returns
validated historical OHLCV observations.

Instrument-specific Yahoo symbols belong in config.py.

Yahoo data is treated as a research / fallback market-data source,
not as authoritative exchange data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf


SOURCE_NAME = "YAHOO"


class YahooError(RuntimeError):
    """Base exception for Yahoo collector errors."""


class YahooDataError(YahooError):
    """Raised when Yahoo returns missing or invalid market data."""


@dataclass(frozen=True, slots=True)
class YahooDataset:
    """
    Validated Yahoo market-data dataset.
    """

    symbol: str
    dataframe: pd.DataFrame
    retrieved_at: datetime
    source: str = SOURCE_NAME


def normalize_symbol(symbol: str) -> str:
    """
    Normalize a Yahoo Finance symbol.
    """

    normalized = symbol.strip().upper()

    if not normalized:
        raise ValueError(
            "Yahoo market-data symbol cannot be empty."
        )

    return normalized


def normalize_dataframe(
    dataframe: pd.DataFrame,
    symbol: str,
) -> pd.DataFrame:
    """
    Convert Yahoo field names into our internal OHLCV schema.
    """

    if dataframe.empty:
        raise YahooDataError(
            f"{SOURCE_NAME} returned no data for {symbol}."
        )

    result = dataframe.copy()

    if isinstance(result.columns, pd.MultiIndex):
        result.columns = [
            column[0]
            if isinstance(column, tuple)
            else column
            for column in result.columns
        ]

    result = result.reset_index()

    rename_map = {
        "Date": "date",
        "Datetime": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adjusted_close",
        "Volume": "volume",
    }

    result = result.rename(
        columns=rename_map
    )

    required = {
        "date",
        "open",
        "high",
        "low",
        "close",
    }

    missing = required - set(result.columns)

    if missing:
        raise YahooDataError(
            f"Unexpected {SOURCE_NAME} schema "
            f"for {symbol}. "
            f"Missing columns: {sorted(missing)}. "
            f"Received columns: {list(result.columns)}"
        )

    result["date"] = pd.to_datetime(
        result["date"],
        errors="coerce",
        utc=True,
    )

    numeric_columns = (
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
    )

    for column in numeric_columns:

        if column not in result.columns:
            continue

        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    result = result.dropna(
        subset=[
            "date",
            "open",
            "high",
            "low",
            "close",
        ]
    )

    result = result.sort_values("date")

    result = result.drop_duplicates(
        subset=["date"],
        keep="last",
    )

    result = result.reset_index(drop=True)

    if result.empty:
        raise YahooDataError(
            f"No valid OHLC observations remain "
            f"for {symbol} after normalization."
        )

    return result


def collect_history(
    symbol: str,
    period: str = "3mo",
    interval: str = "1d",
) -> YahooDataset:
    """
    Download historical market data.

    Parameters
    ----------
    symbol:
        Yahoo Finance instrument symbol.

    period:
        History window understood by yfinance.

    interval:
        Sampling interval understood by yfinance.
    """

    normalized_symbol = normalize_symbol(
        symbol
    )

    try:
        dataframe = yf.download(
            tickers=normalized_symbol,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )

    except Exception as exc:
        raise YahooDataError(
            f"{SOURCE_NAME} request failed "
            f"for {normalized_symbol}: {exc}"
        ) from exc

    dataframe = normalize_dataframe(
        dataframe=dataframe,
        symbol=normalized_symbol,
    )

    return YahooDataset(
        symbol=normalized_symbol,
        dataframe=dataframe,
        retrieved_at=datetime.now(
            timezone.utc
        ),
    )


def latest_row(
    dataset: YahooDataset,
) -> pd.Series:
    """
    Return newest available observation.
    """

    if dataset.dataframe.empty:
        raise YahooDataError(
            f"No observations available "
            f"for {dataset.symbol}."
        )

    return dataset.dataframe.iloc[-1]


def probe(
    symbol: str,
) -> bool:
    """
    Probe one provider symbol.

    Returns True on success and False on failure.
    """

    normalized_symbol = normalize_symbol(
        symbol
    )

    print("=" * 70)
    print("MARKET DATA SOURCE PROBE")
    print("=" * 70)

    print(f"Source: YAHOO")
    print(f"Symbol: {normalized_symbol}")
    print()

    try:
        dataset = collect_history(
            symbol=normalized_symbol,
        )

    except YahooError as exc:
        print("Status: FAILED")
        print(f"Reason: {exc}")
        return False

    dataframe = dataset.dataframe
    latest = latest_row(dataset)

    print("Status: OK")
    print(f"Rows:   {len(dataframe):,}")

    print(
        "Range:  "
        f"{dataframe['date'].iloc[0]} "
        "-> "
        f"{dataframe['date'].iloc[-1]}"
    )

    print(f"Latest open:  {latest['open']}")
    print(f"Latest high:  {latest['high']}")
    print(f"Latest low:   {latest['low']}")
    print(f"Latest close: {latest['close']}")

    if "volume" in dataframe.columns:
        print(
            f"Latest volume: "
            f"{latest['volume']}"
        )

    print(
        f"Retrieved at: "
        f"{dataset.retrieved_at.isoformat()}"
    )

    return True


def main() -> None:
    """
    Collector diagnostic.

    No financial instrument is hardcoded here.
    """

    print("=" * 70)
    print("GENERIC YAHOO COLLECTOR")
    print("=" * 70)

    print(
        "No instrument is hardcoded in this collector."
    )

    print(
        "Supply a Yahoo provider symbol "
        "through the instrument configuration."
    )


if __name__ == "__main__":
    main()