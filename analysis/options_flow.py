"""
Options positioning analysis.

This module converts normalized CME option-chain records into
open-interest and delta-exposure summaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from collectors.cme_options import (
    CMEOptionPoint,
    CMEOptionsChain,
)

from config import InstrumentConfig

from collectors.treasury_rates import (
    TreasuryCurve,
    rate_for_maturity,
)

from models.black76 import (
    implied_volatility,
    option_gamma,
)


@dataclass(frozen=True, slots=True)
class OptionExposure:
    """
    Positioning metrics for one CME option strike.
    """

    series: str
    expiration_code: str
    expiration_date: date | None
    bulletin_date: date | None

    option_type: str

    strike: float
    futures_settlement: float | None
    option_settlement: float | None

    volume: int
    open_interest: int
    delta: float | None

    delta_exposure: float | None
    time_to_expiry: float | None

    risk_free_rate: float | None
    implied_volatility: float | None
    gamma: float | None
    gamma_exposure: float | None
    gex_per_1pct: float | None



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


def calculate_time_to_expiry(
    bulletin_date: date,
    expiration_date: date,
) -> float | None:
    """
    Calculate time to expiration in years.

    Expired contracts return None.
    """

    days = (
        expiration_date
        - bulletin_date
    ).days

    if days <= 0:
        return None

    return days / 365.0


def calculate_gex_per_1pct(
    point: CMEOptionPoint,
    gamma: float,
    instrument: InstrumentConfig,
) -> float:
    """
    Estimate signed gamma exposure for a 1% futures-price move.
    """

    if point.futures_settlement is None:
        raise ValueError(
            "futures settlement is required."
        )

    direction = (
        1.0
        if point.option_type == "CALL"
        else -1.0
    )

    one_percent_move = (
        point.futures_settlement * 0.01
    )

    return (
        direction
        * gamma
        * point.open_interest
        * instrument.point_value
        * one_percent_move
    )


def build_option_exposures(
    chain: CMEOptionsChain,
    instrument: InstrumentConfig,
    curve: TreasuryCurve,
    series: str = "STANDARD",
) -> tuple[OptionExposure, ...]:
    """
    Build positioning metrics for one option series.
    """

    normalized_series = series.strip().upper()

    exposures: list[OptionExposure] = []

    for point in chain.points:

        if point.series != normalized_series:
            continue

        expiration_date = (
            chain.metadata.option_expirations.get(
                point.expiration_code
            )
        )

        time_to_expiry = None
        risk_free_rate = None
        volatility = None
        gamma = None
        gamma_exposure = None
        gex_per_1pct = None

        if expiration_date is not None:
            time_to_expiry = calculate_time_to_expiry(
                bulletin_date=(
                    chain.metadata.bulletin_date
                ),
                expiration_date=expiration_date,
            )

        can_price = (
            time_to_expiry is not None
            and point.futures_settlement is not None
            and point.futures_settlement > 0
            and point.option_settlement is not None
            and point.option_settlement > 0
        )

        if can_price:
            risk_free_rate = rate_for_maturity(
                curve=curve,
                maturity_years=time_to_expiry,
            )

            volatility = implied_volatility(
                market_price=point.option_settlement,
                futures_price=point.futures_settlement,
                strike=point.strike,
                time_to_expiry=time_to_expiry,
                risk_free_rate=risk_free_rate,
                option_type=point.option_type,
            )

            if volatility is not None:
                gamma = option_gamma(
                    futures_price=point.futures_settlement,
                    strike=point.strike,
                    time_to_expiry=time_to_expiry,
                    volatility=volatility,
                    risk_free_rate=risk_free_rate,
                )

                gamma_exposure = (
                    gamma
                    * point.open_interest
                    * instrument.contract_size
                )

                gex_per_1pct = calculate_gex_per_1pct(
                    point=point,
                    gamma=gamma,
                    instrument=instrument,
                )

        exposures.append(
            OptionExposure(
                series=point.series,
                expiration_code=point.expiration_code,
                expiration_date=expiration_date,
                bulletin_date=(
                    chain.metadata.bulletin_date
                ),

                option_type=point.option_type,

                strike=point.strike,
                futures_settlement=(
                    point.futures_settlement
                ),
                option_settlement=(
                    point.option_settlement
                ),

                volume=point.volume,
                open_interest=point.open_interest,
                delta=point.delta,

                delta_exposure=calculate_delta_exposure(
                    point=point,
                    instrument=instrument,
                ),
                time_to_expiry=time_to_expiry,

                risk_free_rate=risk_free_rate,
                implied_volatility=volatility,
                gamma=gamma,
                gamma_exposure=gamma_exposure,
                gex_per_1pct=gex_per_1pct,
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
    
    call_gex_per_1pct: float
    put_gex_per_1pct: float
    net_gex_per_1pct: float


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

        call_gex_per_1pct = sum(
            point.gex_per_1pct or 0.0
            for point in calls
        )

        put_gex_per_1pct = sum(
            point.gex_per_1pct or 0.0
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

                call_gex_per_1pct=call_gex_per_1pct,
                put_gex_per_1pct=put_gex_per_1pct,
                net_gex_per_1pct=(
                    call_gex_per_1pct
                    + put_gex_per_1pct
                ),
            )
        )

    return tuple(results)

@dataclass(frozen=True, slots=True)
class GammaWall:
    """
    One significant gamma-exposure level.
    """

    strike: float
    gex_per_1pct: float


@dataclass(frozen=True, slots=True)
class GammaProfile:
    """
    Gamma-exposure profile for one expiration.
    """

    expiration_code: str
    futures_settlement: float | None
    total_net_gex_per_1pct: float

    top_call_walls: tuple[GammaWall, ...]
    top_put_walls: tuple[GammaWall, ...]
    top_positive_net_walls: tuple[GammaWall, ...]
    top_negative_net_walls: tuple[GammaWall, ...]



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

    call_gex_per_1pct: float
    put_gex_per_1pct: float
    net_gex_per_1pct: float

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

        call_gex_per_1pct = sum(
            point.gex_per_1pct
            for point in calls
            if point.gex_per_1pct is not None
        )

        put_gex_per_1pct = sum(
            point.gex_per_1pct
            for point in puts
            if point.gex_per_1pct is not None
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
                call_gex_per_1pct=(
                    call_gex_per_1pct
                ),
                put_gex_per_1pct=(
                    put_gex_per_1pct
                ),
                net_gex_per_1pct=(
                    call_gex_per_1pct
                    + put_gex_per_1pct
                ),

                missing_delta_open_interest=sum(
                    point.open_interest
                    for point in rows
                    if point.delta is None
                ),
            )
        )

    return tuple(results)



def build_gamma_profile(
    exposures: tuple[OptionExposure, ...],
    expiration_code: str,
    top_n: int = 3,
) -> GammaProfile:
    """
    Build gamma-wall profile for one expiration.
    """

    if top_n <= 0:
        raise ValueError("top_n must be greater than zero.")

    normalized_expiration = expiration_code.strip().upper()

    strikes = aggregate_by_strike(
        exposures=exposures,
        expiration_code=normalized_expiration,
    )

    expiration_rows = [
        point
        for point in exposures
        if point.expiration_code == normalized_expiration
    ]

    futures_settlement = next(
        (
            point.futures_settlement
            for point in expiration_rows
            if point.futures_settlement is not None
        ),
        None,
    )

    top_call = sorted(
        strikes,
        key=lambda x: x.call_gex_per_1pct,
        reverse=True,
    )[:top_n]

    top_put = sorted(
        strikes,
        key=lambda x: x.put_gex_per_1pct,
    )[:top_n]

    top_positive = sorted(
        strikes,
        key=lambda x: x.net_gex_per_1pct,
        reverse=True,
    )[:top_n]

    top_negative = sorted(
        strikes,
        key=lambda x: x.net_gex_per_1pct,
    )[:top_n]

    return GammaProfile(
        expiration_code=normalized_expiration,
        futures_settlement=futures_settlement,
        total_net_gex_per_1pct=sum(
            point.net_gex_per_1pct
            for point in strikes
        ),
        top_call_walls=tuple(
            GammaWall(
                strike=point.strike,
                gex_per_1pct=point.call_gex_per_1pct,
            )
            for point in top_call
        ),
        top_put_walls=tuple(
            GammaWall(
                strike=point.strike,
                gex_per_1pct=point.put_gex_per_1pct,
            )
            for point in top_put
        ),
        top_positive_net_walls=tuple(
            GammaWall(
                strike=point.strike,
                gex_per_1pct=point.net_gex_per_1pct,
            )
            for point in top_positive
        ),
        top_negative_net_walls=tuple(
            GammaWall(
                strike=point.strike,
                gex_per_1pct=point.net_gex_per_1pct,
            )
            for point in top_negative
        ),
    )


def available_expirations(
    chain: CMEOptionsChain,
    series: str = "STANDARD",
) -> tuple[str, ...]:
    """
    Return available expirations in chronological order.
    """

    normalized_series = series.strip().upper()

    available_codes = {
        point.expiration_code
        for point in chain.points
        if (
            point.series == normalized_series
            and point.expiration_code
            in chain.metadata.option_expirations
        )
    }


    return tuple(
        sorted(
            available_codes,
            key=lambda code: chain.metadata.option_expirations[code],
        )
    )

