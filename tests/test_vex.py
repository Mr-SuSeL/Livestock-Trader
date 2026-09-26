import pytest

from analysis.options_flow import calculate_vex_per_1pct_iv
from collectors.cme_options import CMEOptionPoint
from config import get_instrument


def make_point(option_type: str) -> CMEOptionPoint:
    return CMEOptionPoint(
        series="STANDARD",
        expiration_code="OCT26",
        option_type=option_type,
        strike_raw=780,
        strike=78.0,
        futures_settlement=80.0,
        option_settlement=1.0,
        delta=0.5,
        volume=10,
        open_interest=100,
    )


def test_call_vex_scaling():
    instrument = get_instrument("lean_hogs")
    point = make_point("CALL")
    vanna = 0.25

    result = calculate_vex_per_1pct_iv(
        point=point,
        vanna=vanna,
        instrument=instrument,
    )

    expected = (
        0.25
        * 100
        * 400.0
        * 80.0
        * 0.01
    )

    assert result == pytest.approx(expected)
    assert result > 0


def test_put_vex_has_negative_sign():
    instrument = get_instrument("lean_hogs")
    point = make_point("PUT")
    vanna = 0.25

    result = calculate_vex_per_1pct_iv(
        point=point,
        vanna=vanna,
        instrument=instrument,
    )

    expected = -(
        0.25
        * 100
        * 400.0
        * 80.0
        * 0.01
    )

    assert result == pytest.approx(expected)
    assert result < 0