"""
Generic futures term-structure analysis.

This module does not communicate directly with any data provider
except through existing collector interfaces.

Responsibilities:
    - generate candidate futures contracts
    - request contract history through an existing collector
    - build a futures curve
    - calculate adjacent calendar spreads
    - identify liquidity concentration
    - describe curve structure

Instrument-specific metadata belongs in config.py.

Provider-specific HTTP/download logic belongs in collectors/.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import pandas as pd

from collectors.yahoo_futures import (
    YahooDataError,
    collect_history,
    latest_row,
)
from config import InstrumentConfig


MONTH_CODES: dict[int, str] = {
    1: "F",
    2: "G",
    3: "H",
    4: "J",
    5: "K",
    6: "M",
    7: "N",
    8: "Q",
    9: "U",
    10: "V",
    11: "X",
    12: "Z",
}


MONTH_NAMES: dict[int, str] = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}


class FuturesCurveError(RuntimeError):
    """Base exception for futures-curve analysis."""


@dataclass(frozen=True, slots=True)
class ContractCandidate:
    """
    Candidate futures contract that may exist at the provider.
    """

    root: str
    year: int
    month: int

    contract_code: str
    provider_symbol: str

    @property
    def label(self) -> str:
        """
        Human-readable contract label.
        """

        return (
            f"{MONTH_NAMES[self.month]}-"
            f"{str(self.year)[2:]}"
        )


@dataclass(frozen=True, slots=True)
class FuturesCurvePoint:
    """
    One successfully retrieved futures contract.
    """

    contract_code: str
    provider_symbol: str

    year: int
    month: int
    label: str

    price_date: pd.Timestamp

    open: float
    high: float
    low: float
    close: float

    volume: int | None

    spread_previous: float | None = None
    spread_previous_pct: float | None = None


@dataclass(frozen=True, slots=True)
class FuturesCurveAnalysis:
    """
    Complete futures curve snapshot.
    """

    instrument_name: str
    source: str
    retrieved_at: datetime

    points: tuple[FuturesCurvePoint, ...]

    lowest_contract: str | None
    lowest_price: float | None

    highest_contract: str | None
    highest_price: float | None

    most_active_contract: str | None
    most_active_volume: int | None


def yahoo_contract_symbol(
    root: str,
    year: int,
    month: int,
) -> tuple[str, str]:
    """
    Build CME-style contract code and Yahoo provider symbol.

    Example structure:

        root + month code + two-digit year

    followed by the Yahoo CME suffix.
    """

    if month not in MONTH_CODES:
        raise ValueError(
            f"Invalid futures month: {month}"
        )

    if year < 2000:
        raise ValueError(
            f"Invalid futures year: {year}"
        )

    normalized_root = root.strip().upper()

    if not normalized_root:
        raise ValueError(
            "Futures root cannot be empty."
        )

    month_code = MONTH_CODES[month]
    year_code = str(year)[-2:]

    contract_code = (
        f"{normalized_root}"
        f"{month_code}"
        f"{year_code}"
    )

    provider_symbol = (
        f"{contract_code}.CME"
    )

    return contract_code, provider_symbol


def validate_contract_months(
    months: Iterable[int],
) -> tuple[int, ...]:
    """
    Validate and normalize configured futures contract months.
    """

    normalized = tuple(
        sorted(
            set(months)
        )
    )

    if not normalized:
        raise FuturesCurveError(
            "No futures contract months configured."
        )

    invalid = [
        month
        for month in normalized
        if month not in MONTH_CODES
    ]

    if invalid:
        raise FuturesCurveError(
            "Invalid futures contract months: "
            f"{invalid}"
        )

    return normalized


def generate_candidates(
    instrument: InstrumentConfig,
    start_year: int | None = None,
    years_forward: int = 2,
) -> list[ContractCandidate]:
    """
    Generate candidate futures contracts using instrument metadata.
    """

    if start_year is None:
        start_year = datetime.now(
            timezone.utc
        ).year

    if years_forward < 0:
        raise ValueError(
            "years_forward cannot be negative."
        )

    root = (
        instrument.futures_root
        .strip()
        .upper()
    )

    if not root:
        raise FuturesCurveError(
            f"No futures root configured "
            f"for {instrument.name}."
        )

    months = validate_contract_months(
        instrument.contract_months
    )

    candidates: list[ContractCandidate] = []

    for year in range(
        start_year,
        start_year + years_forward + 1,
    ):

        for month in months:

            contract_code, provider_symbol = (
                yahoo_contract_symbol(
                    root=root,
                    year=year,
                    month=month,
                )
            )

            candidates.append(
                ContractCandidate(
                    root=root,
                    year=year,
                    month=month,
                    contract_code=contract_code,
                    provider_symbol=provider_symbol,
                )
            )

    return candidates


def _safe_volume(
    value: object,
) -> int | None:
    """
    Convert provider volume into a safe integer.
    """

    try:

        if pd.isna(value):
            return None

        return int(
            float(value)
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def _candidate_sort_key(
    candidate: ContractCandidate,
) -> tuple[int, int]:
    """
    Sort contract candidates chronologically.
    """

    return (
        candidate.year,
        candidate.month,
    )


def collect_curve_points(
    candidates: Iterable[ContractCandidate],
    period: str = "5d",
) -> list[FuturesCurvePoint]:
    """
    Retrieve candidate contracts through the Yahoo collector.

    Provider symbols that do not produce valid data are skipped.
    """

    points: list[FuturesCurvePoint] = []

    ordered_candidates = sorted(
        candidates,
        key=_candidate_sort_key,
    )

    for candidate in ordered_candidates:

        try:
            dataset = collect_history(
                symbol=candidate.provider_symbol,
                period=period,
                interval="1d",
            )

            row = latest_row(
                dataset
            )

        except YahooDataError:
            continue

        volume = None

        if "volume" in row.index:
            volume = _safe_volume(
                row["volume"]
            )

        point = FuturesCurvePoint(
            contract_code=(
                candidate.contract_code
            ),
            provider_symbol=(
                candidate.provider_symbol
            ),
            year=candidate.year,
            month=candidate.month,
            label=candidate.label,
            price_date=row["date"],
            open=float(
                row["open"]
            ),
            high=float(
                row["high"]
            ),
            low=float(
                row["low"]
            ),
            close=float(
                row["close"]
            ),
            volume=volume,
        )

        points.append(
            point
        )

    return points


def add_calendar_spreads(
    points: Iterable[FuturesCurvePoint],
) -> list[FuturesCurvePoint]:
    """
    Calculate spreads between adjacent available contracts.

    Convention:

        current contract close - previous contract close

    Positive:
        deferred contract is above the previous contract.

    Negative:
        deferred contract is below the previous contract.
    """

    ordered = sorted(
        points,
        key=lambda point: (
            point.year,
            point.month,
        ),
    )

    result: list[FuturesCurvePoint] = []

    previous: FuturesCurvePoint | None = None

    for point in ordered:

        spread = None
        spread_pct = None

        if previous is not None:

            spread = (
                point.close
                - previous.close
            )

            if previous.close != 0:
                spread_pct = (
                    spread
                    / previous.close
                    * 100.0
                )

        result.append(
            FuturesCurvePoint(
                contract_code=(
                    point.contract_code
                ),
                provider_symbol=(
                    point.provider_symbol
                ),
                year=point.year,
                month=point.month,
                label=point.label,
                price_date=point.price_date,
                open=point.open,
                high=point.high,
                low=point.low,
                close=point.close,
                volume=point.volume,
                spread_previous=spread,
                spread_previous_pct=(
                    spread_pct
                ),
            )
        )

        previous = point

    return result


def analyse_curve(
    instrument: InstrumentConfig,
    points: Iterable[FuturesCurvePoint],
) -> FuturesCurveAnalysis:
    """
    Produce descriptive futures-curve statistics.

    This function intentionally does not turn the curve into a
    trading signal.
    """

    ordered = tuple(
        sorted(
            points,
            key=lambda point: (
                point.year,
                point.month,
            ),
        )
    )

    if not ordered:
        raise FuturesCurveError(
            f"No futures contracts available "
            f"for {instrument.name}."
        )

    lowest = min(
        ordered,
        key=lambda point: point.close,
    )

    highest = max(
        ordered,
        key=lambda point: point.close,
    )

    volume_points = [
        point
        for point in ordered
        if point.volume is not None
    ]

    if volume_points:

        most_active = max(
            volume_points,
            key=lambda point: (
                point.volume
                if point.volume is not None
                else 0
            ),
        )

        most_active_contract = (
            most_active.contract_code
        )

        most_active_volume = (
            most_active.volume
        )

    else:

        most_active_contract = None
        most_active_volume = None

    return FuturesCurveAnalysis(
        instrument_name=instrument.name,
        source="YAHOO",
        retrieved_at=datetime.now(
            timezone.utc
        ),
        points=ordered,
        lowest_contract=(
            lowest.contract_code
        ),
        lowest_price=(
            lowest.close
        ),
        highest_contract=(
            highest.contract_code
        ),
        highest_price=(
            highest.close
        ),
        most_active_contract=(
            most_active_contract
        ),
        most_active_volume=(
            most_active_volume
        ),
    )


def build_curve(
    instrument: InstrumentConfig,
    years_forward: int = 2,
    period: str = "5d",
) -> FuturesCurveAnalysis:
    """
    Run the high-level futures-curve pipeline.
    """

    candidates = generate_candidates(
        instrument=instrument,
        years_forward=years_forward,
    )

    points = collect_curve_points(
        candidates=candidates,
        period=period,
    )

    points = add_calendar_spreads(
        points
    )

    return analyse_curve(
        instrument=instrument,
        points=points,
    )


def print_curve(
    analysis: FuturesCurveAnalysis,
) -> None:
    """
    Print a human-readable futures curve snapshot.
    """

    print("=" * 90)

    print(
        f"{analysis.instrument_name.upper()} "
        f"FUTURES CURVE"
    )

    print("=" * 90)

    print(
        f"{'Contract':<10}"
        f"{'Month':<10}"
        f"{'Date':<14}"
        f"{'Close':>10}"
        f"{'Volume':>12}"
        f"{'Spread':>12}"
        f"{'Spread %':>12}"
    )

    print("-" * 90)

    for point in analysis.points:

        if point.volume is None:
            volume_text = "-"
        else:
            volume_text = (
                f"{point.volume:,}"
            )

        if point.spread_previous is None:
            spread_text = "-"
        else:
            spread_text = (
                f"{point.spread_previous:+.3f}"
            )

        if point.spread_previous_pct is None:
            spread_pct_text = "-"
        else:
            spread_pct_text = (
                f"{point.spread_previous_pct:+.2f}%"
            )

        date_text = (
            point.price_date.strftime(
                "%Y-%m-%d"
            )
        )

        print(
            f"{point.contract_code:<10}"
            f"{point.label:<10}"
            f"{date_text:<14}"
            f"{point.close:>10.3f}"
            f"{volume_text:>12}"
            f"{spread_text:>12}"
            f"{spread_pct_text:>12}"
        )

    print()
    print("-" * 90)

    print(
        f"Curve low:          "
        f"{analysis.lowest_contract} "
        f"@ {analysis.lowest_price:.3f}"
    )

    print(
        f"Curve high:         "
        f"{analysis.highest_contract} "
        f"@ {analysis.highest_price:.3f}"
    )

    if analysis.most_active_contract:

        most_active_volume = (
            analysis.most_active_volume
            if analysis.most_active_volume is not None
            else 0
        )

        print(
            f"Most active:        "
            f"{analysis.most_active_contract} "
            f"(volume "
            f"{most_active_volume:,})"
        )

    else:

        print(
            "Most active:        "
            "UNKNOWN"
        )

    print()

    print(
        f"Source:             "
        f"{analysis.source}"
    )

    print(
        f"Retrieved at:       "
        f"{analysis.retrieved_at.isoformat()}"
    )