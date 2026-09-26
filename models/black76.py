"""
Black-76 model for options on futures.
"""

from __future__ import annotations

import math


_SQRT_TWO = math.sqrt(2.0)
_SQRT_TWO_PI = math.sqrt(2.0 * math.pi)


def _normal_cdf(
    value: float,
) -> float:
    """
    Standard normal cumulative distribution function.
    """

    return 0.5 * (
        1.0
        + math.erf(
            value / _SQRT_TWO
        )
    )


def _normal_pdf(
    value: float,
) -> float:
    """
    Standard normal probability density function.
    """

    return (
        math.exp(
            -0.5 * value * value
        )
        / _SQRT_TWO_PI
    )


def _validate_inputs(
    futures_price: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
) -> None:
    """
    Validate Black-76 model inputs.
    """

    if futures_price <= 0:
        raise ValueError(
            "futures_price must be greater than zero."
        )

    if strike <= 0:
        raise ValueError(
            "strike must be greater than zero."
        )

    if time_to_expiry <= 0:
        raise ValueError(
            "time_to_expiry must be greater than zero."
        )

    if volatility <= 0:
        raise ValueError(
            "volatility must be greater than zero."
        )


def d1_d2(
    futures_price: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
) -> tuple[float, float]:
    """
    Calculate Black-76 d1 and d2.
    """

    _validate_inputs(
        futures_price=futures_price,
        strike=strike,
        time_to_expiry=time_to_expiry,
        volatility=volatility,
    )

    volatility_time = (
        volatility
        * math.sqrt(time_to_expiry)
    )

    d1 = (
        math.log(
            futures_price / strike
        )
        + 0.5
        * volatility
        * volatility
        * time_to_expiry
    ) / volatility_time

    d2 = d1 - volatility_time

    return d1, d2


def option_delta(
    futures_price: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    risk_free_rate: float,
    option_type: str,
) -> float:
    """
    Calculate Black-76 option delta with respect to futures price.
    """

    d1, _ = d1_d2(
        futures_price=futures_price,
        strike=strike,
        time_to_expiry=time_to_expiry,
        volatility=volatility,
    )

    discount = math.exp(
        -risk_free_rate
        * time_to_expiry
    )

    normalized_type = (
        option_type
        .strip()
        .upper()
    )

    if normalized_type == "CALL":
        return (
            discount
            * _normal_cdf(d1)
        )

    if normalized_type == "PUT":
        return (
            discount
            * (
                _normal_cdf(d1)
                - 1.0
            )
        )

    raise ValueError(
        "option_type must be CALL or PUT."
    )


def option_gamma(
    futures_price: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    risk_free_rate: float,
) -> float:
    """
    Calculate Black-76 gamma with respect to futures price.
    """

    d1, _ = d1_d2(
        futures_price=futures_price,
        strike=strike,
        time_to_expiry=time_to_expiry,
        volatility=volatility,
    )

    discount = math.exp(
        -risk_free_rate
        * time_to_expiry
    )

    return (
        discount
        * _normal_pdf(d1)
        / (
            futures_price
            * volatility
            * math.sqrt(time_to_expiry)
        )
    )


def option_vanna(
    futures_price: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    risk_free_rate: float,
) -> float:
    """
    Calculate Black-76 vanna with respect to futures price
    and volatility.
    """

    d1, d2 = d1_d2(
        futures_price=futures_price,
        strike=strike,
        time_to_expiry=time_to_expiry,
        volatility=volatility,
    )

    discount = math.exp(
        -risk_free_rate
        * time_to_expiry
    )

    return (
        -discount
        * _normal_pdf(d1)
        * d2
        / volatility
    )




def option_price(
    futures_price: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    risk_free_rate: float,
    option_type: str,
) -> float:
    """
    Calculate Black-76 option price.
    """

    d1, d2 = d1_d2(
        futures_price=futures_price,
        strike=strike,
        time_to_expiry=time_to_expiry,
        volatility=volatility,
    )

    discount = math.exp(
        -risk_free_rate * time_to_expiry
    )

    normalized_type = option_type.strip().upper()

    if normalized_type == "CALL":
        return discount * (
            futures_price * _normal_cdf(d1)
            - strike * _normal_cdf(d2)
        )

    if normalized_type == "PUT":
        return discount * (
            strike * _normal_cdf(-d2)
            - futures_price * _normal_cdf(-d1)
        )

    raise ValueError(
        "option_type must be CALL or PUT."
    )


def implied_volatility(
    market_price: float,
    futures_price: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    option_type: str,
    tolerance: float = 1e-8,
    max_iterations: int = 200,
) -> float | None:
    """
    Solve Black-76 implied volatility by bisection.

    Return None when the market price does not admit
    a valid positive-volatility solution.
    """

    if market_price <= 0:
        return None

    if futures_price <= 0:
        return None

    if strike <= 0:
        return None

    if time_to_expiry <= 0:
        return None

    normalized_type = option_type.strip().upper()

    if normalized_type not in {"CALL", "PUT"}:
        raise ValueError(
            "option_type must be CALL or PUT."
        )

    discount = math.exp(
        -risk_free_rate * time_to_expiry
    )

    if normalized_type == "CALL":
        lower_bound = discount * max(
            futures_price - strike,
            0.0,
        )
        upper_bound = discount * futures_price

    else:
        lower_bound = discount * max(
            strike - futures_price,
            0.0,
        )
        upper_bound = discount * strike

    if (
        market_price <= lower_bound
        or market_price >= upper_bound
    ):
        return None

    low_volatility = 1e-6
    high_volatility = 5.0

    low_price = option_price(
        futures_price=futures_price,
        strike=strike,
        time_to_expiry=time_to_expiry,
        volatility=low_volatility,
        risk_free_rate=risk_free_rate,
        option_type=normalized_type,
    )

    high_price = option_price(
        futures_price=futures_price,
        strike=strike,
        time_to_expiry=time_to_expiry,
        volatility=high_volatility,
        risk_free_rate=risk_free_rate,
        option_type=normalized_type,
    )

    if not (
        low_price <= market_price <= high_price
    ):
        return None

    for _ in range(max_iterations):

        volatility = (
            low_volatility
            + high_volatility
        ) / 2.0

        model_price = option_price(
            futures_price=futures_price,
            strike=strike,
            time_to_expiry=time_to_expiry,
            volatility=volatility,
            risk_free_rate=risk_free_rate,
            option_type=normalized_type,
        )

        error = model_price - market_price

        if abs(error) <= tolerance:
            return volatility

        if error < 0:
            low_volatility = volatility
        else:
            high_volatility = volatility

    return None
