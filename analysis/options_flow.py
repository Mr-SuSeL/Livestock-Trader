"""
Options positioning analysis.

This module converts normalized CME option-chain records into
open-interest and delta-exposure summaries.
"""

from __future__ import annotations

from dataclasses import dataclass

from collectors.cme_options import CMEOptionPoint
from config import InstrumentConfig


@dataclass(frozen=True, slots=True)
class OptionExposure:
    """
    Positioning metrics for one CME option strike.
    """

    series: str
    expiration_code: str
    option_type: str

    strike: float
    futures_settlement: float | None

    volume: int
    open_interest: int
    delta: float | None

    delta_exposure: float | None


def calculate_delta_exposure(
    point: CMEOptionPoint,
    instrument: InstrumentConfig,
) -> float | None:
    """
    Calculate open-interest-weighted delta exposure.

    CME put deltas are represented as positive absolute values in the
    bulletin, so puts are assigned a negative directional sign here.
    """

    if point.delta is None:
        return None

    direction = (
        1.0
        if point.option_type == "CALL"
        else -1.0
    )

    return (
        direction
        * point.delta
        * point.open_interest
        * instrument.contract_size
    )


def build_option_exposures(
    points: tuple[CMEOptionPoint, ...],
    instrument: InstrumentConfig,
    series: str = "STANDARD",
) -> tuple[OptionExposure, ...]:
    """
    Build positioning metrics for one option series.
    """

    normalized_series = series.strip().upper()

    exposures: list[OptionExposure] = []

    for point in points:

        if point.series != normalized_series:
            continue

        exposures.append(
            OptionExposure(
                series=point.series,
                expiration_code=point.expiration_code,
                option_type=point.option_type,
                strike=point.strike,
                futures_settlement=point.futures_settlement,
                volume=point.volume,
                open_interest=point.open_interest,
                delta=point.delta,
                delta_exposure=calculate_delta_exposure(
                    point=point,
                    instrument=instrument,
                ),
            )
        )

    return tuple(exposures)

# delta=0.000   # CME rzeczywiście podało 0.000
# delta=None    # CME nie podało numerycznej delty

@dataclass(frozen=True, slots=True)
class ExpirationExposure:
    """
    Aggregated option positioning for one expiration.
    """

    expiration_code: str

    call_open_interest: int
    put_open_interest: int

    call_delta_open_interest: int
    put_delta_open_interest: int

    call_missing_delta_open_interest: int
    put_missing_delta_open_interest: int

    call_volume: int
    put_volume: int

    call_delta_exposure: float
    put_delta_exposure: float
    net_delta_exposure: float


def aggregate_by_expiration(
    exposures: tuple[OptionExposure, ...],
) -> tuple[ExpirationExposure, ...]:
    """
    Aggregate option positioning by expiration.
    """

    expiration_codes = sorted(
        {
            point.expiration_code
            for point in exposures
        }
    )

    results: list[ExpirationExposure] = []

    for expiration_code in expiration_codes:

        rows = [
            point
            for point in exposures
            if point.expiration_code == expiration_code
        ]

        calls = [
            point
            for point in rows
            if point.option_type == "CALL"
        ]

        puts = [
            point
            for point in rows
            if point.option_type == "PUT"
        ]

        call_delta_exposure = sum(
            point.delta_exposure or 0.0
            for point in calls
        )

        put_delta_exposure = sum(
            point.delta_exposure or 0.0
            for point in puts
        )

        results.append(
            ExpirationExposure(
                expiration_code=expiration_code,

                call_open_interest=sum(
                    point.open_interest
                    for point in calls
                ),
                put_open_interest=sum(
                    point.open_interest
                    for point in puts
                ),

                call_delta_open_interest=sum(
                    point.open_interest
                    for point in calls
                    if point.delta is not None
                ),
                put_delta_open_interest=sum(
                    point.open_interest
                    for point in puts
                    if point.delta is not None
                ),

                call_missing_delta_open_interest=sum(
                    point.open_interest
                    for point in calls
                    if point.delta is None
                ),
                put_missing_delta_open_interest=sum(
                    point.open_interest
                    for point in puts
                    if point.delta is None
                ),

                call_volume=sum(
                    point.volume
                    for point in calls
                ),
                put_volume=sum(
                    point.volume
                    for point in puts
                ),

                call_delta_exposure=call_delta_exposure,
                put_delta_exposure=put_delta_exposure,
                net_delta_exposure=(
                    call_delta_exposure
                    + put_delta_exposure
                ),
            )
        )

    return tuple(results)

@dataclass(frozen=True, slots=True)
class StrikeExposure:
    """
    Aggregated option positioning for one strike.
    """

    expiration_code: str
    strike: float

    call_open_interest: int
    put_open_interest: int
    net_open_interest: int

    call_volume: int
    put_volume: int

    call_delta_exposure: float
    put_delta_exposure: float
    net_delta_exposure: float

    missing_delta_open_interest: int


def aggregate_by_strike(
    exposures: tuple[OptionExposure, ...],
    expiration_code: str,
) -> tuple[StrikeExposure, ...]:
    """
    Aggregate option positioning by strike for one expiration.
    """

    normalized_expiration = (
        expiration_code
        .strip()
        .upper()
    )

    expiration_rows = [
        point
        for point in exposures
        if point.expiration_code
        == normalized_expiration
    ]

    strikes = sorted(
        {
            point.strike
            for point in expiration_rows
        }
    )

    results: list[StrikeExposure] = []

    for strike in strikes:

        rows = [
            point
            for point in expiration_rows
            if point.strike == strike
        ]

        calls = [
            point
            for point in rows
            if point.option_type == "CALL"
        ]

        puts = [
            point
            for point in rows
            if point.option_type == "PUT"
        ]

        call_open_interest = sum(
            point.open_interest
            for point in calls
        )

        put_open_interest = sum(
            point.open_interest
            for point in puts
        )

        call_delta_exposure = sum(
            point.delta_exposure
            for point in calls
            if point.delta_exposure is not None
        )

        put_delta_exposure = sum(
            point.delta_exposure
            for point in puts
            if point.delta_exposure is not None
        )

        results.append(
            StrikeExposure(
                expiration_code=(
                    normalized_expiration
                ),
                strike=strike,

                call_open_interest=(
                    call_open_interest
                ),
                put_open_interest=(
                    put_open_interest
                ),
                net_open_interest=(
                    call_open_interest
                    - put_open_interest
                ),

                call_volume=sum(
                    point.volume
                    for point in calls
                ),
                put_volume=sum(
                    point.volume
                    for point in puts
                ),

                call_delta_exposure=(
                    call_delta_exposure
                ),
                put_delta_exposure=(
                    put_delta_exposure
                ),
                net_delta_exposure=(
                    call_delta_exposure
                    + put_delta_exposure
                ),

                missing_delta_open_interest=sum(
                    point.open_interest
                    for point in rows
                    if point.delta is None
                ),
            )
        )

    return tuple(results)