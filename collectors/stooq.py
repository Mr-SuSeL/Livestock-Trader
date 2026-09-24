"""
Generic Stooq historical market-data collector.

The collector contains no instrument-specific configuration.

It receives a symbol from the caller, retrieves data, validates the
response and returns normalized observations.

Instrument/provider symbol mappings belong in config.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO

import pandas as pd
import requests


SOURCE_NAME = "STOOQ"

BASE_DOWNLOAD_URL = "https://stooq.com/q/d/l/"

REQUEST_TIMEOUT = 20


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,text/plain,*/*",
}


class StooqError(RuntimeError):
    """Base exception for Stooq collector errors."""


class StooqHTTPError(StooqError):
    """Raised when Stooq returns an unsuccessful HTTP response."""


class StooqDataError(StooqError):
    """Raised when returned data cannot be validated."""


@dataclass(frozen=True, slots=True)
class StooqDataset:
    """
    Validated dataset returned by Stooq.
    """

    symbol: str

    dataframe: pd.DataFrame

    retrieved_at: datetime

    source: str = SOURCE_NAME


def normalize_symbol(symbol: str) -> str:
    """
    Normalize a provider symbol supplied by the caller.
    """

    normalized = symbol.strip().upper()

    if not normalized:
        raise ValueError(
            "Market-data symbol cannot be empty."
        )

    return normalized


def build_download_params(
    symbol: str,
) -> dict[str, str]:
    """
    Construct request parameters for daily historical data.
    """

    return {
        "s": normalize_symbol(symbol).lower(),
        "i": "d",
    }


def fetch_raw(
    symbol: str,
) -> requests.Response:
    """
    Perform transport only.

    The returned content is validated separately.
    """

    normalized_symbol = normalize_symbol(symbol)

    response = requests.get(
        BASE_DOWNLOAD_URL,
        params=build_download_params(
            normalized_symbol
        ),
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code != 200:
        raise StooqHTTPError(
            f"{SOURCE_NAME} returned HTTP "
            f"{response.status_code} for "
            f"{normalized_symbol}."
        )

    return response


def is_html(text: str) -> bool:
    """
    Detect common HTML responses.
    """

    content = text.lstrip().lower()

    return (
        content.startswith("<!doctype")
        or content.startswith("<html")
        or "<html" in content[:500]
    )


def parse_csv(
    text: str,
    symbol: str,
) -> pd.DataFrame:
    """
    Parse and validate a CSV response.
    """

    content = text.strip()

    if not content:
        raise StooqDataError(
            f"{SOURCE_NAME} returned an empty "
            f"response for {symbol}."
        )

    if is_html(content):
        raise StooqDataError(
            f"{SOURCE_NAME} returned HTML instead "
            f"of market-data CSV for {symbol}."
        )

    try:
        dataframe = pd.read_csv(
            StringIO(content)
        )

    except Exception as exc:
        raise StooqDataError(
            f"Unable to parse {SOURCE_NAME} "
            f"response for {symbol}: {exc}"
        ) from exc

    return normalize_dataframe(
        dataframe=dataframe,
        symbol=symbol,
    )


def normalize_dataframe(
    dataframe: pd.DataFrame,
    symbol: str,
) -> pd.DataFrame:
    """
    Normalize external field names into the internal schema.
    """

    if dataframe.empty:
        raise StooqDataError(
            f"{SOURCE_NAME} returned no rows "
            f"for {symbol}."
        )

    rename_map = {
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
        "Open Interest": "open_interest",
        "OpenInterest": "open_interest",
    }

    result = dataframe.rename(
        columns=rename_map
    ).copy()

    required = {
        "date",
        "open",
        "high",
        "low",
        "close",
    }

    missing = required - set(result.columns)

    if missing:
        raise StooqDataError(
            f"Unexpected {SOURCE_NAME} schema "
            f"for {symbol}. "
            f"Missing: {sorted(missing)}. "
            f"Received: {list(result.columns)}"
        )

    result["date"] = pd.to_datetime(
        result["date"],
        errors="coerce",
    )

    numeric_columns = (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "open_interest",
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
        raise StooqDataError(
            f"No valid OHLC observations remain "
            f"for {symbol} after normalization."
        )

    return result


def collect_history(
    symbol: str,
) -> StooqDataset:
    """
    Retrieve historical market data for any supplied symbol.
    """

    normalized_symbol = normalize_symbol(
        symbol
    )

    response = fetch_raw(
        normalized_symbol
    )

    dataframe = parse_csv(
        text=response.text,
        symbol=normalized_symbol,
    )

    return StooqDataset(
        symbol=normalized_symbol,
        dataframe=dataframe,
        retrieved_at=datetime.now(
            timezone.utc
        ),
    )


def probe(
    symbol: str,
) -> None:
    """
    Diagnostic probe for one externally supplied symbol.
    """

    normalized_symbol = normalize_symbol(
        symbol
    )

    print("=" * 70)
    print("MARKET DATA SOURCE PROBE")
    print("=" * 70)

    print(f"Source: {SOURCE_NAME}")
    print(f"Symbol: {normalized_symbol}")

    print()

    try:
        dataset = collect_history(
            normalized_symbol
        )

    except (
        StooqError,
        requests.RequestException,
    ) as exc:

        print("Status: FAILED")
        print(f"Reason: {exc}")

        return

    dataframe = dataset.dataframe

    latest = dataframe.iloc[-1]

    print("Status: OK")
    print(f"Rows:   {len(dataframe):,}")

    print(
        "Range:  "
        f"{dataframe['date'].iloc[0].date()} "
        "-> "
        f"{dataframe['date'].iloc[-1].date()}"
    )

    print(
        f"Latest close: {latest['close']}"
    )

    print(
        f"Retrieved at: "
        f"{dataset.retrieved_at.isoformat()}"
    )


def main() -> None:
    """
    Standalone execution intentionally requires no
    instrument-specific assumptions.

    Use this module through main.py or import probe()
    from an interactive session.
    """

    print("=" * 70)
    print("GENERIC STOOQ COLLECTOR")
    print("=" * 70)

    print(
        "No instrument is hardcoded in this collector."
    )

    print(
        "Pass a provider symbol from the application "
        "configuration."
    )


if __name__ == "__main__":
    main()