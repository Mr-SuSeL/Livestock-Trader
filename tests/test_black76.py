import pytest

from models.black76 import option_delta, option_vanna


def test_option_vanna_matches_numeric_delta_derivative():
    futures_price = 100.0
    strike = 100.0
    time_to_expiry = 0.5
    volatility = 0.25
    risk_free_rate = 0.04
    bump = 1e-5

    analytic = option_vanna(
        futures_price,
        strike,
        time_to_expiry,
        volatility,
        risk_free_rate,
    )

    numeric = (
        option_delta(
            futures_price,
            strike,
            time_to_expiry,
            volatility + bump,
            risk_free_rate,
            "CALL",
        )
        - option_delta(
            futures_price,
            strike,
            time_to_expiry,
            volatility - bump,
            risk_free_rate,
            "CALL",
        )
    ) / (2.0 * bump)

    assert analytic == pytest.approx(
        numeric,
        rel=1e-8,
        abs=1e-10,
    )