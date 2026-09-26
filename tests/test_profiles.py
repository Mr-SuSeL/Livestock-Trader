import pytest

from analysis.options_flow import (
    OptionExposure,
    build_gamma_profile,
    build_vanna_profile,
    build_trader_profile,
)


def make_exposure(
    strike: float,
    option_type: str,
    gex: float,
    vex: float,
) -> OptionExposure:
    return OptionExposure(
        series="STANDARD",
        expiration_code="OCT26",
        expiration_date=None,
        bulletin_date=None,
        option_type=option_type,
        strike=strike,
        futures_settlement=80.0,
        option_settlement=1.0,
        volume=10,
        open_interest=100,
        delta=0.5,
        delta_exposure=0.0,
        time_to_expiry=0.1,
        risk_free_rate=0.04,
        implied_volatility=0.20,
        gamma=0.05,
        gamma_exposure=0.0,
        gex_per_1pct=gex,
        vanna=0.25,
        vex_per_1pct_iv=vex,
    )


@pytest.fixture
def exposures():
    rows = []

    for index, strike in enumerate(
        (76.0, 77.0, 78.0, 79.0, 80.0, 81.0)
    ):
        scale = float(index + 1)

        rows.append(
            make_exposure(
                strike=strike,
                option_type="CALL",
                gex=100.0 * scale,
                vex=1000.0 * scale,
            )
        )

        rows.append(
            make_exposure(
                strike=strike,
                option_type="PUT",
                gex=-50.0 * scale,
                vex=-400.0 * scale,
            )
        )

    return tuple(rows)


@pytest.mark.parametrize("top_n", [1, 3, 5])
def test_gamma_profile_respects_top_n(exposures, top_n):
    profile = build_gamma_profile(
        exposures,
        "OCT26",
        top_n=top_n,
    )

    assert len(profile.top_call_walls) == top_n
    assert len(profile.top_put_walls) == top_n
    assert len(profile.top_positive_net_walls) == top_n
    assert len(profile.top_negative_net_walls) == top_n


@pytest.mark.parametrize("top_n", [1, 3, 5])
def test_vanna_profile_respects_top_n(exposures, top_n):
    profile = build_vanna_profile(
        exposures,
        "OCT26",
        top_n=top_n,
    )

    assert len(profile.top_call_walls) == top_n
    assert len(profile.top_put_walls) == top_n
    assert len(profile.top_positive_net_walls) == top_n
    assert len(profile.top_negative_net_walls) == top_n


def test_trader_profile_combines_gamma_and_vanna(exposures):
    profile = build_trader_profile(
        exposures,
        "OCT26",
        top_n=3,
    )

    assert profile.expiration_code == "OCT26"
    assert profile.futures_settlement == 80.0

    assert len(profile.gamma.top_call_walls) == 3
    assert len(profile.vanna.top_call_walls) == 3

    assert profile.gamma.top_call_walls[0].strike == 81.0
    assert profile.vanna.top_call_walls[0].strike == 81.0


@pytest.mark.parametrize(
    "builder",
    [
        build_gamma_profile,
        build_vanna_profile,
        build_trader_profile,
    ],
)
def test_profiles_reject_invalid_top_n(exposures, builder):
    with pytest.raises(ValueError):
        builder(
            exposures,
            "OCT26",
            top_n=0,
        )