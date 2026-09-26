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
    option_vanna,
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

    vanna: float | None
    vex_per_1pct_iv: float | None



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


def calculate_vex_per_1pct_iv(
    point: CMEOptionPoint,
    vanna: float,
    instrument: InstrumentConfig,
) -> float:
    """
    Estimate signed vanna exposure for a 1 percentage-point IV move.
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

    iv_move = 0.01

    return (
        direction
        * vanna
        * point.open_interest
        * instrument.point_value
        * point.futures_settlement
        * iv_move
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
        vanna = None
        vex_per_1pct_iv = None

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

                vanna = option_vanna(
                    futures_price=point.futures_settlement,
                    strike=point.strike,
                    time_to_expiry=time_to_expiry,
                    volatility=volatility,
                    risk_free_rate=risk_free_rate,
                )

                vex_per_1pct_iv = calculate_vex_per_1pct_iv(
                    point=point,
                    vanna=vanna,
                    instrument=instrument,
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
                vanna=vanna,
                vex_per_1pct_iv=vex_per_1pct_iv,
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

    call_vex_per_1pct_iv: float
    put_vex_per_1pct_iv: float
    net_vex_per_1pct_iv: float



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

        call_vex_per_1pct_iv = sum(
            point.vex_per_1pct_iv or 0.0
            for point in calls
        )

        put_vex_per_1pct_iv = sum(
            point.vex_per_1pct_iv or 0.0
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

                call_vex_per_1pct_iv=call_vex_per_1pct_iv,
                put_vex_per_1pct_iv=put_vex_per_1pct_iv,
                net_vex_per_1pct_iv=(
                    call_vex_per_1pct_iv
                    + put_vex_per_1pct_iv
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
class VannaWall:
    """
    One significant vanna-exposure level.
    """

    strike: float
    vex_per_1pct_iv: float


@dataclass(frozen=True, slots=True)
class VannaProfile:
    """
    Vanna-exposure profile for one expiration.
    """

    expiration_code: str
    futures_settlement: float | None
    total_net_vex_per_1pct_iv: float

    top_call_walls: tuple[VannaWall, ...]
    top_put_walls: tuple[VannaWall, ...]
    top_positive_net_walls: tuple[VannaWall, ...]
    top_negative_net_walls: tuple[VannaWall, ...]


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
class RelativeWall:
    """
    Exposure wall positioned relative to futures settlement.
    """

    strike: float
    exposure: float
    distance_points: float
    distance_percent: float



def build_relative_wall(
    strike: float,
    exposure: float,
    futures_settlement: float,
) -> RelativeWall:
    """
    Position an exposure wall relative to futures settlement.
    """

    if futures_settlement <= 0:
        raise ValueError(
            "futures_settlement must be greater than zero."
        )

    distance_points = strike - futures_settlement

    return RelativeWall(
        strike=strike,
        exposure=exposure,
        distance_points=distance_points,
        distance_percent=(
            distance_points
            / futures_settlement
            * 100.0
        ),
    )


def find_nearest_walls(
    walls: tuple[RelativeWall, ...],
    futures_settlement: float,
) -> tuple[RelativeWall | None, RelativeWall | None]:
    """
    Find nearest exposure walls below and above futures settlement.
    """

    below = [
        wall
        for wall in walls
        if wall.strike < futures_settlement
    ]

    above = [
        wall
        for wall in walls
        if wall.strike > futures_settlement
    ]

    nearest_below = max(
        below,
        key=lambda wall: wall.strike,
        default=None,
    )

    nearest_above = min(
        above,
        key=lambda wall: wall.strike,
        default=None,
    )

    return nearest_below, nearest_above


@dataclass(frozen=True, slots=True)
class TraderProfile:
    """
    Combined options positioning profile for one expiration.
    """

    expiration_code: str
    futures_settlement: float | None

    gamma: GammaProfile
    vanna: VannaProfile
    gex_zones: tuple["GEXZone", ...]


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

    call_vex_per_1pct_iv: float
    put_vex_per_1pct_iv: float
    net_vex_per_1pct_iv: float


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

        call_vex_per_1pct_iv = sum(
            point.vex_per_1pct_iv
            for point in calls
            if point.vex_per_1pct_iv is not None
        )

        put_vex_per_1pct_iv = sum(
            point.vex_per_1pct_iv
            for point in puts
            if point.vex_per_1pct_iv is not None
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
                call_vex_per_1pct_iv=(
                    call_vex_per_1pct_iv
                ),
                put_vex_per_1pct_iv=(
                    put_vex_per_1pct_iv
                ),
                net_vex_per_1pct_iv=(
                    call_vex_per_1pct_iv
                    + put_vex_per_1pct_iv
                ),

                missing_delta_open_interest=sum(
                    point.open_interest
                    for point in rows
                    if point.delta is None
                ),
            )
        )

    return tuple(results)


@dataclass(frozen=True, slots=True)
class GEXZone:
    expiration_code: str

    low_strike: float
    high_strike: float
    peak_strike: float

    net_gex_per_1pct: float
    peak_gex_per_1pct: float

    strike_count: int
    strength: float


def _gex_significance_cutoff(
    rows: list[StrikeExposure],
) -> float:
    """
    Find a data-driven cutoff separating background GEX
    from significant GEX concentrations.

    The split minimizes within-group squared error in
    log(abs(GEX)) space. This makes the result scale-invariant
    and avoids fixed absolute thresholds or Top-N selection.
    """
    import math

    values = sorted(
        abs(row.net_gex_per_1pct)
        for row in rows
        if row.net_gex_per_1pct != 0.0
    )

    if not values:
        return float("inf")

    if len(values) == 1:
        return values[0]

    logs = [math.log(value) for value in values]

    prefix_sum = [0.0]
    prefix_sq_sum = [0.0]

    for value in logs:
        prefix_sum.append(prefix_sum[-1] + value)
        prefix_sq_sum.append(prefix_sq_sum[-1] + value * value)

    def squared_error(start: int, end: int) -> float:
        count = end - start

        if count <= 0:
            return 0.0

        total = prefix_sum[end] - prefix_sum[start]
        total_sq = prefix_sq_sum[end] - prefix_sq_sum[start]

        return total_sq - (total * total / count)

    best_split = 1
    best_error = float("inf")

    for split in range(1, len(values)):
        error = (
            squared_error(0, split)
            + squared_error(split, len(values))
        )

        if error < best_error:
            best_error = error
            best_split = split

    return values[best_split]


def _natural_strike_spacing(
    rows: list[StrikeExposure],
) -> float:
    strikes = sorted({row.strike for row in rows})

    gaps = [
        right - left
        for left, right in zip(strikes, strikes[1:])
        if right > left
    ]

    if not gaps:
        return float("inf")

    gap_counts: dict[float, int] = {}

    for gap in gaps:
        gap_counts[gap] = gap_counts.get(gap, 0) + 1

    ordered = sorted(gap_counts.items())

    if len(ordered) == 1:
        return ordered[0][0]

    drops = []

    for index in range(len(ordered) - 1):
        _, current_count = ordered[index]
        _, next_count = ordered[index + 1]

        drops.append(
            current_count / next_count
            if next_count > 0
            else float("inf")
        )

    split_index = max(
        range(len(drops)),
        key=drops.__getitem__,
    )

    return ordered[split_index][0]

def build_gex_zones(
    exposures: tuple[StrikeExposure, ...] | list[StrikeExposure],
) -> tuple[GEXZone, ...]:
    if not exposures:
        return ()

    expirations: dict[str, list[StrikeExposure]] = {}

    for row in exposures:
        expirations.setdefault(
            row.expiration_code,
            [],
        ).append(row)

    zones: list[GEXZone] = []

    for expiration_code, rows in expirations.items():
        rows = sorted(rows, key=lambda row: row.strike)

        cutoff = _gex_significance_cutoff(rows)
        spacing = _natural_strike_spacing(rows)

        significant = [
            row
            for row in rows
            if abs(row.net_gex_per_1pct) >= cutoff
        ]

        if not significant:
            continue

        total_abs_gex = sum(
            abs(row.net_gex_per_1pct)
            for row in rows
        )

        clusters: list[list[StrikeExposure]] = []

        for row in significant:
            if (
                not clusters
                or row.strike - clusters[-1][-1].strike > spacing
            ):
                clusters.append([row])
            else:
                clusters[-1].append(row)

        for cluster in clusters:
            peak = max(
                cluster,
                key=lambda row: abs(row.net_gex_per_1pct),
            )

            net_gex = sum(
                row.net_gex_per_1pct
                for row in cluster
            )

            cluster_abs_gex = sum(
                abs(row.net_gex_per_1pct)
                for row in cluster
            )

            strength = (
                cluster_abs_gex / total_abs_gex
                if total_abs_gex > 0.0
                else 0.0
            )

            zones.append(
                GEXZone(
                    expiration_code=expiration_code,
                    low_strike=cluster[0].strike,
                    high_strike=cluster[-1].strike,
                    peak_strike=peak.strike,
                    net_gex_per_1pct=net_gex,
                    peak_gex_per_1pct=peak.net_gex_per_1pct,
                    strike_count=len(cluster),
                    strength=strength,
                )
            )

    return tuple(zones)



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

def build_vanna_profile(
    exposures: tuple[OptionExposure, ...],
    expiration_code: str,
    top_n: int = 3,
) -> VannaProfile:
    """
    Build vanna-wall profile for one expiration.
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
        key=lambda x: x.call_vex_per_1pct_iv,
        reverse=True,
    )[:top_n]

    top_put = sorted(
        strikes,
        key=lambda x: x.put_vex_per_1pct_iv,
    )[:top_n]

    top_positive = sorted(
        strikes,
        key=lambda x: x.net_vex_per_1pct_iv,
        reverse=True,
    )[:top_n]

    top_negative = sorted(
        strikes,
        key=lambda x: x.net_vex_per_1pct_iv,
    )[:top_n]

    return VannaProfile(
        expiration_code=normalized_expiration,
        futures_settlement=futures_settlement,
        total_net_vex_per_1pct_iv=sum(
            point.net_vex_per_1pct_iv
            for point in strikes
        ),
        top_call_walls=tuple(
            VannaWall(
                strike=point.strike,
                vex_per_1pct_iv=point.call_vex_per_1pct_iv,
            )
            for point in top_call
        ),
        top_put_walls=tuple(
            VannaWall(
                strike=point.strike,
                vex_per_1pct_iv=point.put_vex_per_1pct_iv,
            )
            for point in top_put
        ),
        top_positive_net_walls=tuple(
            VannaWall(
                strike=point.strike,
                vex_per_1pct_iv=point.net_vex_per_1pct_iv,
            )
            for point in top_positive
        ),
        top_negative_net_walls=tuple(
            VannaWall(
                strike=point.strike,
                vex_per_1pct_iv=point.net_vex_per_1pct_iv,
            )
            for point in top_negative
        ),
    )


def build_trader_profile(
    exposures: tuple[OptionExposure, ...],
    expiration_code: str,
    top_n: int = 3,
) -> TraderProfile:
    """
    Build combined GEX, VEX and GEX-zone trader profile.
    """

    gamma = build_gamma_profile(
        exposures=exposures,
        expiration_code=expiration_code,
        top_n=top_n,
    )

    vanna = build_vanna_profile(
        exposures=exposures,
        expiration_code=expiration_code,
        top_n=top_n,
    )

    strikes = aggregate_by_strike(
        exposures=exposures,
        expiration_code=gamma.expiration_code,
    )

    gex_zones = build_gex_zones(strikes)

    return TraderProfile(
        expiration_code=gamma.expiration_code,
        futures_settlement=gamma.futures_settlement,
        gamma=gamma,
        vanna=vanna,
        gex_zones=gex_zones,
    )
