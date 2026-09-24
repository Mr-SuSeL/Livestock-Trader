"""
Generic market-regime analytics.

This module transforms normalized market data into descriptive
price and positioning statistics.

It does not download data directly and does not contain
instrument-specific configuration.

Responsibilities:
    - price returns
    - realized volatility
    - drawdown
    - percentile ranks
    - CFTC net positioning
    - weekly CFTC changes
    - open-interest changes

Trading signals and composite scores belong in a separate layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

import numpy as np
import pandas as pd


class RegimeError(RuntimeError):
    """Base exception for regime-analysis errors."""


@dataclass(frozen=True, slots=True)
class PriceRegime:
    """
    Descriptive statistics for a price series.
    """

    observations: int

    latest_date: pd.Timestamp
    latest_close: float

    return_1m_pct: float | None
    return_3m_pct: float | None

    realized_volatility_pct: float | None

    drawdown_pct: float | None

    close_percentile: float | None


@dataclass(frozen=True, slots=True)
class PositioningMetric:
    """
    Current state of one CFTC participant category.
    """

    net: float

    change_1w: float | None

    percentile: float | None


@dataclass(frozen=True, slots=True)
class CFTCRegime:
    """
    Descriptive CFTC positioning statistics.
    """

    observations: int

    latest_report_date: pd.Timestamp

    open_interest: float
    open_interest_change_1w: float | None
    open_interest_change_1w_pct: float | None

    producer: PositioningMetric | None
    swap: PositioningMetric | None
    managed_money: PositioningMetric | None
    other_reportable: PositioningMetric | None


def percentile_rank(
    values: pd.Series,
    current_value: float,
) -> float | None:
    """
    Return percentile rank of current_value within historical values.

    Result is expressed on a 0-100 scale.
    """

    numeric = pd.to_numeric(
        values,
        errors="coerce",
    ).dropna()

    if numeric.empty:
        return None

    less_or_equal = (
        numeric <= current_value
    ).sum()

    return float(
        less_or_equal
        / len(numeric)
        * 100.0
    )


def _return_over_observations(
    close: pd.Series,
    periods: int,
) -> float | None:
    """
    Calculate percentage return over a number of observations.
    """

    if periods <= 0:
        raise ValueError(
            "periods must be greater than zero."
        )

    if len(close) <= periods:
        return None

    previous = float(
        close.iloc[-periods - 1]
    )

    current = float(
        close.iloc[-1]
    )

    if previous == 0:
        return None

    return (
        current / previous - 1.0
    ) * 100.0


def analyse_price_regime(
    dataframe: pd.DataFrame,
    volatility_window: int = 20,
) -> PriceRegime:
    """
    Analyse normalized daily OHLCV price history.

    The input dataframe is expected to contain:
        date
        close
    """

    required = {
        "date",
        "close",
    }

    missing = required - set(
        dataframe.columns
    )

    if missing:
        raise RegimeError(
            "Price dataframe is missing columns: "
            f"{sorted(missing)}"
        )

    frame = dataframe.copy()

    frame["date"] = pd.to_datetime(
        frame["date"],
        errors="coerce",
        utc=True,
    )

    frame["close"] = pd.to_numeric(
        frame["close"],
        errors="coerce",
    )

    frame = frame.dropna(
        subset=[
            "date",
            "close",
        ]
    )

    frame = frame.sort_values(
        "date"
    )

    frame = frame.drop_duplicates(
        subset=["date"],
        keep="last",
    )

    frame = frame.reset_index(
        drop=True
    )

    if frame.empty:
        raise RegimeError(
            "No valid price observations."
        )

    close = frame["close"]

    latest_close = float(
        close.iloc[-1]
    )

    return_1m = _return_over_observations(
        close,
        periods=21,
    )

    return_3m = _return_over_observations(
        close,
        periods=63,
    )

    daily_returns = (
        close.pct_change()
        .replace(
            [np.inf, -np.inf],
            np.nan,
        )
        .dropna()
    )

    realized_volatility = None

    if len(daily_returns) >= volatility_window:

        recent_returns = daily_returns.iloc[
            -volatility_window:
        ]

        daily_std = float(
            recent_returns.std(
                ddof=1
            )
        )

        realized_volatility = (
            daily_std
            * sqrt(252.0)
            * 100.0
        )

    running_high = close.cummax()

    drawdown = (
        close / running_high - 1.0
    )

    latest_drawdown = float(
        drawdown.iloc[-1]
        * 100.0
    )

    close_percentile = percentile_rank(
        close,
        latest_close,
    )

    return PriceRegime(
        observations=len(frame),
        latest_date=frame["date"].iloc[-1],
        latest_close=latest_close,
        return_1m_pct=return_1m,
        return_3m_pct=return_3m,
        realized_volatility_pct=(
            realized_volatility
        ),
        drawdown_pct=latest_drawdown,
        close_percentile=(
            close_percentile
        ),
    )


def _positioning_metric(
    dataframe: pd.DataFrame,
    long_column: str,
    short_column: str,
) -> PositioningMetric | None:
    """
    Build one CFTC positioning metric from long/short columns.
    """

    if (
        long_column not in dataframe.columns
        or short_column not in dataframe.columns
    ):
        return None

    long_values = pd.to_numeric(
        dataframe[long_column],
        errors="coerce",
    )

    short_values = pd.to_numeric(
        dataframe[short_column],
        errors="coerce",
    )

    net = (
        long_values
        - short_values
    )

    valid_net = net.dropna()

    if valid_net.empty:
        return None

    latest_net = float(
        valid_net.iloc[-1]
    )

    change_1w = None

    if len(valid_net) >= 2:
        change_1w = float(
            valid_net.iloc[-1]
            - valid_net.iloc[-2]
        )

    percentile = percentile_rank(
        valid_net,
        latest_net,
    )

    return PositioningMetric(
        net=latest_net,
        change_1w=change_1w,
        percentile=percentile,
    )


def analyse_cftc_regime(
    dataframe: pd.DataFrame,
) -> CFTCRegime:
    """
    Analyse normalized CFTC positioning history.

    The dataframe should contain one row per CFTC report date.
    """

    required = {
        "report_date",
        "open_interest",
    }

    missing = required - set(
        dataframe.columns
    )

    if missing:
        raise RegimeError(
            "CFTC dataframe is missing columns: "
            f"{sorted(missing)}"
        )

    frame = dataframe.copy()

    frame["report_date"] = pd.to_datetime(
        frame["report_date"],
        errors="coerce",
        utc=True,
    )

    frame["open_interest"] = pd.to_numeric(
        frame["open_interest"],
        errors="coerce",
    )

    frame = frame.dropna(
        subset=[
            "report_date",
            "open_interest",
        ]
    )

    frame = frame.sort_values(
        "report_date"
    )

    frame = frame.drop_duplicates(
        subset=["report_date"],
        keep="last",
    )

    frame = frame.reset_index(
        drop=True
    )

    if frame.empty:
        raise RegimeError(
            "No valid CFTC observations."
        )

    latest_oi = float(
        frame["open_interest"].iloc[-1]
    )

    oi_change = None
    oi_change_pct = None

    if len(frame) >= 2:

        previous_oi = float(
            frame["open_interest"].iloc[-2]
        )

        oi_change = (
            latest_oi
            - previous_oi
        )

        if previous_oi != 0:
            oi_change_pct = (
                oi_change
                / previous_oi
                * 100.0
            )

    producer = _positioning_metric(
        frame,
        "producer_long",
        "producer_short",
    )

    swap = _positioning_metric(
        frame,
        "swap_long",
        "swap_short",
    )

    managed_money = _positioning_metric(
        frame,
        "managed_money_long",
        "managed_money_short",
    )

    other_reportable = _positioning_metric(
        frame,
        "other_reportable_long",
        "other_reportable_short",
    )

    return CFTCRegime(
        observations=len(frame),
        latest_report_date=(
            frame["report_date"].iloc[-1]
        ),
        open_interest=latest_oi,
        open_interest_change_1w=(
            oi_change
        ),
        open_interest_change_1w_pct=(
            oi_change_pct
        ),
        producer=producer,
        swap=swap,
        managed_money=managed_money,
        other_reportable=(
            other_reportable
        ),
    )


def _format_optional(
    value: float | None,
    decimals: int = 2,
    suffix: str = "",
) -> str:
    """
    Format an optional numeric value.
    """

    if value is None:
        return "N/A"

    return (
        f"{value:,.{decimals}f}"
        f"{suffix}"
    )


def print_price_regime(
    regime: PriceRegime,
) -> None:
    """
    Print price-regime statistics.
    """

    print("=" * 70)
    print("PRICE REGIME")
    print("=" * 70)

    print(
        f"Latest date:       "
        f"{regime.latest_date}"
    )

    print(
        f"Latest close:      "
        f"{regime.latest_close:,.3f}"
    )

    print(
        f"Return 1M:         "
        f"{_format_optional(regime.return_1m_pct, 2, '%')}"
    )

    print(
        f"Return 3M:         "
        f"{_format_optional(regime.return_3m_pct, 2, '%')}"
    )

    print(
        f"Realized vol:      "
        f"{_format_optional(regime.realized_volatility_pct, 2, '%')}"
    )

    print(
        f"Drawdown:          "
        f"{_format_optional(regime.drawdown_pct, 2, '%')}"
    )

    print(
        f"Close percentile:  "
        f"{_format_optional(regime.close_percentile, 1, '%')}"
    )


def print_cftc_regime(
    regime: CFTCRegime,
) -> None:
    """
    Print CFTC-regime statistics.
    """

    print("=" * 70)
    print("CFTC POSITIONING REGIME")
    print("=" * 70)

    print(
        f"Report date:       "
        f"{regime.latest_report_date}"
    )

    print(
        f"Open interest:     "
        f"{regime.open_interest:,.0f}"
    )

    print(
        f"OI change 1W:      "
        f"{_format_optional(regime.open_interest_change_1w, 0)}"
    )

    print(
        f"OI change 1W %:    "
        f"{_format_optional(regime.open_interest_change_1w_pct, 2, '%')}"
    )

    metrics = (
        ("Producer", regime.producer),
        ("Swap", regime.swap),
        ("Managed Money", regime.managed_money),
        ("Other Reportable", regime.other_reportable),
    )

    print()

    for label, metric in metrics:
        if metric is None:
            print(f"{label}: N/A")
            continue

        print(label)

        print(
            f"  Net:             "
            f"{metric.net:+,.0f}"
        )

        print(
            f"  Change 1W:       "
            f"{_format_optional(metric.change_1w, 0)}"
        )

        print(
            f"  Percentile:      "
            f"{_format_optional(metric.percentile, 1, '%')}"
        )

        print()