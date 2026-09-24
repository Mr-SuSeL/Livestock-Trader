"""
Official CME Lean Hogs futures data adapter.

This module intentionally does NOT scrape CME Group web pages or use
undocumented CME quote endpoints.

During development of Lean Hogs Lab an undocumented CME quote endpoint
was tested and returned HTTP 403 with an explicit anti-scraping message.

Therefore this module is reserved for a future CME source that is:

1. documented or explicitly downloadable,
2. accessible without bypassing anti-bot protections,
3. available under conditions acceptable for this project,
4. usable without a paid market-data subscription.

Until such a source is validated, calling collect_futures() fails
explicitly instead of silently returning fallback or stale data.

Fallback market-data providers belong in separate collectors.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


SOURCE_NAME = "CME"

SOURCE_STATUS = "UNAVAILABLE"

SOURCE_REASON = (
    "No validated free automated CME futures source is currently configured."
)


class CMEDataUnavailable(RuntimeError):
    """Raised when an approved CME data source is not configured."""


@dataclass(frozen=True, slots=True)
class CMEFuturesQuote:
    """
    Normalized representation of a Lean Hogs futures quote.

    This is the schema we want the future CME collector to produce.
    Not every source necessarily provides every field.
    """

    symbol: str
    contract_month: str
    contract_year: int

    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    last: Optional[float] = None
    change: Optional[float] = None
    settlement: Optional[float] = None

    volume: Optional[int] = None
    open_interest: Optional[int] = None
    open_interest_change: Optional[int] = None

    market_timestamp: Optional[datetime] = None
    retrieved_at: Optional[datetime] = None

    source: str = SOURCE_NAME


def source_available() -> bool:
    """
    Return True only when an approved automated CME source has
    actually been implemented and validated.
    """

    return False


def source_status() -> dict[str, str | bool]:
    """
    Return machine-readable CME collector status.

    The dashboard will eventually use information like this to display
    data-source health.
    """

    return {
        "source": SOURCE_NAME,
        "available": source_available(),
        "status": SOURCE_STATUS,
        "reason": SOURCE_REASON,
    }


def collect_futures() -> list:
    """
    Collect Lean Hogs futures data from an approved CME source.

    Currently unavailable by design.

    We DO NOT automatically substitute another provider here because
    doing so would make data provenance ambiguous. Fallback selection
    will be performed by a higher-level market data layer.
    """

    raise CMEDataUnavailable(
        f"{SOURCE_NAME}: {SOURCE_REASON}"
    )


def main() -> None:
    """
    Small diagnostic entry point.

    Running:

        python -m collectors.cme_futures

    should clearly show that CME automation is currently disabled.
    """

    status = source_status()

    print("=" * 70)
    print("LEAN HOGS LAB - CME FUTURES")
    print("=" * 70)

    print(f"Source:    {status['source']}")
    print(f"Available: {status['available']}")
    print(f"Status:    {status['status']}")
    print(f"Reason:    {status['reason']}")

    print()
    print(
        "No request was sent to CME. "
        "This collector is intentionally disabled."
    )


if __name__ == "__main__":
    main()