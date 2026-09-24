"""
Generic CFTC Commitments of Traders collector.

This collector retrieves positioning data from the official
CFTC Public Reporting / Socrata dataset.

It contains no commodity-specific configuration.

Instrument-specific CFTC identifiers belong in config.py.

Initial dataset
---------------
Disaggregated Futures Only

The collector is designed around stable CFTC identifiers rather
than commodity names wherever possible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests


SOURCE_NAME = "CFTC"

BASE_URL = (
    "https://publicreporting.cftc.gov/"
    "resource/72hh-3qpy.json"
)

REQUEST_TIMEOUT = 30


class CFTCError(RuntimeError):
    """Base exception for CFTC collector errors."""


class CFTCHTTPError(CFTCError):
    """Raised when CFTC returns an HTTP error."""


class CFTCDataError(CFTCError):
    """Raised when returned CFTC data is invalid."""


@dataclass(frozen=True, slots=True)
class CFTCDataset:
    """
    Validated CFTC positioning dataset.
    """

    dataframe: pd.DataFrame
    retrieved_at: datetime
    source: str = SOURCE_NAME
    dataset: str = "disaggregated_futures_only"


def fetch_json(
    params: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve raw rows from the official CFTC dataset.
    """

    try:
        response = requests.get(
            BASE_URL,
            params=params,
            timeout=REQUEST_TIMEOUT,
            headers={
                "Accept": "application/json",
                "User-Agent": (
                    "market-lab/0.1 "
                    "personal-research"
                ),
            },
        )

    except requests.RequestException as exc:
        raise CFTCHTTPError(
            f"CFTC request failed: {exc}"
        ) from exc

    if response.status_code != 200:
        raise CFTCHTTPError(
            f"CFTC returned HTTP "
            f"{response.status_code}. "
            f"URL: {response.url}"
        )

    try:
        payload = response.json()

    except requests.JSONDecodeError as exc:
        raise CFTCDataError(
            "CFTC returned invalid JSON."
        ) from exc

    if not isinstance(payload, list):
        raise CFTCDataError(
            "Unexpected CFTC response type: "
            f"{type(payload).__name__}"
        )

    return payload


def normalize_dataframe(
    rows: list[dict[str, Any]],
) -> pd.DataFrame:
    """
    Convert CFTC JSON rows into normalized internal fields.
    """

    if not rows:
        raise CFTCDataError(
            "CFTC returned no rows."
        )

    dataframe = pd.DataFrame(rows)

    rename_map = {
        "market_and_exchange_names": (
            "market_and_exchange"
        ),
        "report_date_as_yyyy_mm_dd": (
            "report_date"
        ),
        "contract_market_name": (
            "contract_market_name"
        ),
        "cftc_contract_market_code": (
            "contract_market_code"
        ),
        "cftc_market_code": (
            "market_code"
        ),
        "cftc_commodity_code": (
            "commodity_code"
        ),
        "commodity_name": (
            "commodity_name"
        ),
        "open_interest_all": (
            "open_interest"
        ),
        "prod_merc_positions_long": (
            "producer_long"
        ),
        "prod_merc_positions_short": (
            "producer_short"
        ),
        "swap_positions_long_all": (
            "swap_long"
        ),
        "swap__positions_short_all": (
            "swap_short"
        ),
        "m_money_positions_long_all": (
            "managed_money_long"
        ),
        "m_money_positions_short_all": (
            "managed_money_short"
        ),
        "other_rept_positions_long": (
            "other_reportable_long"
        ),
        "other_rept_positions_short": (
            "other_reportable_short"
        ),
    }

    available_map = {
        source: target
        for source, target in rename_map.items()
        if source in dataframe.columns
    }

    dataframe = dataframe.rename(
        columns=available_map
    )

    required = {
        "market_and_exchange",
        "report_date",
        "contract_market_code",
        "commodity_name",
        "open_interest",
    }

    missing = required - set(
        dataframe.columns
    )

    if missing:
        raise CFTCDataError(
            "Unexpected CFTC schema. "
            f"Missing fields: {sorted(missing)}. "
            f"Received fields: "
            f"{list(dataframe.columns)}"
        )

    dataframe["report_date"] = pd.to_datetime(
        dataframe["report_date"],
        errors="coerce",
        utc=True,
    )

    numeric_columns = (
        "open_interest",
        "producer_long",
        "producer_short",
        "swap_long",
        "swap_short",
        "managed_money_long",
        "managed_money_short",
        "other_reportable_long",
        "other_reportable_short",
    )

    for column in numeric_columns:

        if column not in dataframe.columns:
            continue

        dataframe[column] = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        )

    dataframe = dataframe.dropna(
        subset=[
            "report_date",
            "contract_market_code",
        ]
    )

    dataframe = dataframe.sort_values(
        "report_date"
    )

    dataframe = dataframe.reset_index(
        drop=True
    )

    if dataframe.empty:
        raise CFTCDataError(
            "No valid CFTC observations remain "
            "after normalization."
        )

    return dataframe


def collect_by_market_code(
    market_code: str,
    limit: int = 10,
) -> CFTCDataset:
    """
    Retrieve recent COT observations for a CFTC contract market.

    The market code is supplied by application configuration.
    """

    normalized_code = market_code.strip()

    if not normalized_code:
        raise ValueError(
            "CFTC contract market code cannot be empty."
        )

    if limit <= 0:
        raise ValueError(
            "Limit must be greater than zero."
        )

    params = {
        "$where": (
            "cftc_contract_market_code="
            f"'{normalized_code}'"
        ),
        "$order": (
            "report_date_as_yyyy_mm_dd DESC"
        ),
        "$limit": str(limit),
    }

    rows = fetch_json(
        params=params
    )

    dataframe = normalize_dataframe(
        rows
    )

    return CFTCDataset(
        dataframe=dataframe,
        retrieved_at=datetime.now(
            timezone.utc
        ),
    )


def discover_markets(
    search_text: str,
    limit: int = 20,
) -> pd.DataFrame:
    """
    Search the CFTC dataset for candidate markets.

    This function is intended for configuration discovery,
    not routine market-data collection.

    It deliberately searches by text first so we can discover
    the official stable CFTC contract market code.
    """

    query = search_text.strip()

    if not query:
        raise ValueError(
            "CFTC market search text cannot be empty."
        )

    safe_query = query.replace(
        "'",
        "''",
    ).upper()

    params = {
        "$select": (
            "market_and_exchange_names,"
            "contract_market_name,"
            "cftc_contract_market_code,"
            "cftc_market_code,"
            "cftc_commodity_code,"
            "commodity_name"
        ),
        "$where": (
            "upper(market_and_exchange_names) "
            f"like '%{safe_query}%'"
        ),
        "$group": (
            "market_and_exchange_names,"
            "contract_market_name,"
            "cftc_contract_market_code,"
            "cftc_market_code,"
            "cftc_commodity_code,"
            "commodity_name"
        ),
        "$limit": str(limit),
    }

    rows = fetch_json(
        params=params
    )

    if not rows:
        raise CFTCDataError(
            f"No CFTC markets matched {query!r}."
        )

    dataframe = pd.DataFrame(rows)

    return dataframe.reset_index(
        drop=True
    )


def add_positioning_metrics(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Add derived net-position columns.

    These are simple arithmetic transformations of CFTC
    long and short position counts.
    """

    result = dataframe.copy()

    pairs = {
        "producer_net": (
            "producer_long",
            "producer_short",
        ),
        "swap_net": (
            "swap_long",
            "swap_short",
        ),
        "managed_money_net": (
            "managed_money_long",
            "managed_money_short",
        ),
        "other_reportable_net": (
            "other_reportable_long",
            "other_reportable_short",
        ),
    }

    for output, (
        long_column,
        short_column,
    ) in pairs.items():

        if (
            long_column in result.columns
            and short_column in result.columns
        ):
            result[output] = (
                result[long_column]
                - result[short_column]
            )

    return result


def probe_discovery(
    search_text: str,
) -> bool:
    """
    Discover candidate CFTC market identifiers.
    """

    print("=" * 70)
    print("CFTC MARKET DISCOVERY")
    print("=" * 70)

    print(f"Search: {search_text}")
    print()

    try:
        dataframe = discover_markets(
            search_text
        )

    except CFTCError as exc:
        print("Status: FAILED")
        print(f"Reason: {exc}")
        return False

    print("Status: OK")
    print(f"Matches: {len(dataframe)}")
    print()

    columns = [
        column
        for column in (
            "market_and_exchange_names",
            "contract_market_name",
            "cftc_contract_market_code",
            "cftc_market_code",
            "cftc_commodity_code",
            "commodity_name",
        )
        if column in dataframe.columns
    ]

    print(
        dataframe[columns].to_string(
            index=False
        )
    )

    return True


def main() -> None:
    """
    Standalone collector diagnostic.
    """

    print("=" * 70)
    print("GENERIC CFTC COLLECTOR")
    print("=" * 70)

    print(
        "No commodity is hardcoded in this collector."
    )

    print(
        "Use probe_discovery(search_text) to discover "
        "a CFTC market code, then store that code "
        "in instrument configuration."
    )


if __name__ == "__main__":
    main()