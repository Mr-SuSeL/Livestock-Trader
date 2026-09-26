import pytest

from analysis.options_flow import StrikeExposure, build_gex_zones


def exposure(
    strike: float,
    gex: float,
    expiration: str = "TEST",
) -> StrikeExposure:
    return StrikeExposure(
        expiration_code=expiration,
        strike=strike,
        call_open_interest=0,
        put_open_interest=0,
        net_open_interest=0,
        call_volume=0,
        put_volume=0,
        call_delta_exposure=0.0,
        put_delta_exposure=0.0,
        net_delta_exposure=0.0,
        call_gex_per_1pct=0.0,
        put_gex_per_1pct=0.0,
        net_gex_per_1pct=gex,
        call_vex_per_1pct_iv=0.0,
        put_vex_per_1pct_iv=0.0,
        net_vex_per_1pct_iv=0.0,
        missing_delta_open_interest=0,
    )


def test_build_gex_zones_detects_cluster_and_peak():
    rows = [
        exposure(90, 1),
        exposure(91, 2),
        exposure(92, 3),
        exposure(93, 40),
        exposure(94, -70),
        exposure(95, 50),
        exposure(96, 3),
        exposure(97, 2),
    ]

    zones = build_gex_zones(rows)

    assert len(zones) == 1

    zone = zones[0]
    assert zone.expiration_code == "TEST"
    assert zone.low_strike == 93
    assert zone.high_strike == 95
    assert zone.peak_strike == 94
    assert zone.net_gex_per_1pct == pytest.approx(20)
    assert zone.peak_gex_per_1pct == pytest.approx(-70)
    assert zone.strike_count == 3

    total_abs_gex = 1 + 2 + 3 + 40 + 70 + 50 + 3 + 2
    zone_abs_gex = 40 + 70 + 50

    assert zone.strength == pytest.approx(
        zone_abs_gex / total_abs_gex
    )


def test_build_gex_zones_learns_non_unit_spacing():
    rows = [
        exposure(90.0, 1),
        exposure(92.5, 2),
        exposure(95.0, 40),
        exposure(97.5, 70),
        exposure(100.0, 50),
        exposure(102.5, 2),
        exposure(105.0, 1),
    ]

    zones = build_gex_zones(rows)

    assert len(zones) == 1
    assert zones[0].low_strike == 95.0
    assert zones[0].high_strike == 100.0
    assert zones[0].strike_count == 3


def test_build_gex_zones_keeps_expirations_separate():
    rows = [
        exposure(90, 1, "OCT26"),
        exposure(91, 50, "OCT26"),
        exposure(92, 60, "OCT26"),
        exposure(90, 1, "DEC26"),
        exposure(91, 70, "DEC26"),
        exposure(92, 80, "DEC26"),
    ]

    zones = build_gex_zones(rows)

    assert {zone.expiration_code for zone in zones} == {
        "OCT26",
        "DEC26",
    }


def test_build_gex_zones_is_scale_invariant():
    values = [
        (90, 1),
        (91, 2),
        (92, 40),
        (93, 70),
        (94, 50),
        (95, 2),
    ]

    normal = build_gex_zones(
        [exposure(strike, gex) for strike, gex in values]
    )
    scaled = build_gex_zones(
        [exposure(strike, gex * 1000) for strike, gex in values]
    )

    normal_geometry = [
        (z.low_strike, z.high_strike, z.peak_strike, z.strike_count)
        for z in normal
    ]
    scaled_geometry = [
        (z.low_strike, z.high_strike, z.peak_strike, z.strike_count)
        for z in scaled
    ]

    assert scaled_geometry == normal_geometry

def test_build_gex_zones_empty():
    assert build_gex_zones([]) == ()


def test_build_gex_zones_splits_distinct_clusters():
    rows = [
        exposure(90, 1),
        exposure(91, 2),
        exposure(92, 3),
        exposure(93, 40),
        exposure(94, 70),
        exposure(95, 50),
        exposure(96, 2),
        exposure(97, 1),
        exposure(98, 2),
        exposure(99, 3),
        exposure(100, 60),
        exposure(101, 90),
        exposure(102, 50),
        exposure(103, 2),
    ]

    zones = build_gex_zones(rows)

    assert len(zones) == 2

    assert (zones[0].low_strike, zones[0].high_strike) == (93, 95)
    assert zones[0].peak_strike == 94

    assert (zones[1].low_strike, zones[1].high_strike) == (100, 102)
    assert zones[1].peak_strike == 101
