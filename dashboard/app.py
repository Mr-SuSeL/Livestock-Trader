from nicegui import run, ui

from analysis.options_flow import (
    build_relative_wall,
    find_nearest_walls,
)
from config import INSTRUMENTS
from dashboard.state import DashboardState


state = DashboardState()

INSTRUMENT_OPTIONS = {
    key: f"{instrument.name} ({instrument.futures_root})"
    for key, instrument in INSTRUMENTS.items()
}

WALL_OPTIONS = {
    1: "1",
    3: "3",
    5: "5",
    10: "10",
}


def format_number(value: float | None) -> str:
    if value is None:
        return "-"

    absolute = abs(value)

    if absolute >= 1_000_000:
        return f"{value / 1_000_000:+.2f}m"

    if absolute >= 1_000:
        return f"{value / 1_000:+.1f}k"

    return f"{value:+.2f}"


def wall_rows(walls, exposure_field: str):
    futures = state.build_profile().futures_settlement

    rows = []

    for wall in walls:
        exposure = getattr(wall, exposure_field)

        if futures is not None:
            relative = build_relative_wall(
                strike=wall.strike,
                exposure=exposure,
                futures_settlement=futures,
            )

            distance = f"{relative.distance_points:+.2f}"
            distance_pct = f"{relative.distance_percent:+.2f}%"
        else:
            distance = "-"
            distance_pct = "-"

        rows.append(
            {
                "strike": f"{wall.strike:.2f}",
                "exposure": format_number(exposure),
                "distance": distance,
                "distance_pct": distance_pct,
            }
        )

    return rows


def nearest_rows(profile):
    futures = profile.futures_settlement

    if futures is None:
        return []

    groups = (
        (
            "GEX positive",
            profile.gamma.top_positive_net_walls,
            "gex_per_1pct",
        ),
        (
            "GEX negative",
            profile.gamma.top_negative_net_walls,
            "gex_per_1pct",
        ),
        (
            "VEX positive",
            profile.vanna.top_positive_net_walls,
            "vex_per_1pct_iv",
        ),
        (
            "VEX negative",
            profile.vanna.top_negative_net_walls,
            "vex_per_1pct_iv",
        ),
    )

    result = []

    for label, walls, field in groups:
        relative_walls = tuple(
            build_relative_wall(
                strike=wall.strike,
                exposure=getattr(wall, field),
                futures_settlement=futures,
            )
            for wall in walls
        )

        below, above = find_nearest_walls(
            relative_walls,
            futures,
        )

        for side, wall in (
            ("Below", below),
            ("Above", above),
        ):
            if wall is None:
                continue

            result.append(
                {
                    "type": label,
                    "side": side,
                    "strike": f"{wall.strike:.2f}",
                    "distance": f"{wall.distance_points:+.2f}",
                    "distance_pct": (
                        f"{wall.distance_percent:+.2f}%"
                    ),
                }
            )

    return result


def make_wall_table(title: str):
    with ui.card().classes("w-full"):
        ui.label(title).classes(
            "text-lg font-semibold"
        )

        table = ui.table(
            columns=[
                {
                    "name": "strike",
                    "label": "Strike",
                    "field": "strike",
                },
                {
                    "name": "exposure",
                    "label": "Exposure",
                    "field": "exposure",
                },
                {
                    "name": "distance",
                    "label": "Distance",
                    "field": "distance",
                },
                {
                    "name": "distance_pct",
                    "label": "Distance %",
                    "field": "distance_pct",
                },
            ],
            rows=[],
        ).classes("w-full")

    return table


async def refresh_profile():
    if not state.loaded:
        return

    try:
        state.top_n = int(walls_select.value)

        selected = expiration_select.value

        if selected:
            state.select_expiration(selected)

        profile = state.build_profile()

        futures_value.set_text(
            f"{profile.futures_settlement:.2f}"
            if profile.futures_settlement is not None
            else "-"
        )

        net_gex_value.set_text(
            format_number(
                profile.gamma.total_net_gex_per_1pct
            )
        )

        net_vex_value.set_text(
            format_number(
                profile.vanna.total_net_vex_per_1pct_iv
            )
        )

        zones_value.set_text(
            str(len(profile.gex_zones))
        )

        pricing_rows = [
            row
            for row in state.exposures
            if (
                row.expiration_code
                == profile.expiration_code
            )
        ]

        iv_available = sum(
            1
            for row in pricing_rows
            if row.implied_volatility is not None
        )

        data_rows_value.set_text(
            str(len(pricing_rows))
        )

        if pricing_rows:
            iv_coverage = (
                iv_available
                / len(pricing_rows)
                * 100.0
            )
        else:
            iv_coverage = 0.0

        iv_value.set_text(
            f"{iv_coverage:.1f}%"
        )

        expiration_value.set_text(
            profile.expiration_code
        )

        gamma_positive.rows = wall_rows(
            profile.gamma.top_positive_net_walls,
            "gex_per_1pct",
        )
        gamma_positive.update()

        gamma_negative.rows = wall_rows(
            profile.gamma.top_negative_net_walls,
            "gex_per_1pct",
        )
        gamma_negative.update()

        vanna_positive.rows = wall_rows(
            profile.vanna.top_positive_net_walls,
            "vex_per_1pct_iv",
        )
        vanna_positive.update()

        vanna_negative.rows = wall_rows(
            profile.vanna.top_negative_net_walls,
            "vex_per_1pct_iv",
        )
        vanna_negative.update()

        nearest_table.rows = nearest_rows(profile)
        nearest_table.update()

        zone_table.rows = [
            {
                "zone": (
                    f"{zone.low_strike:.2f}"
                    f" - {zone.high_strike:.2f}"
                ),
                "peak": f"{zone.peak_strike:.2f}",
                "net_gex": format_number(
                    zone.net_gex_per_1pct
                ),
                "peak_gex": format_number(
                    zone.peak_gex_per_1pct
                ),
                "strikes": zone.strike_count,
                "strength": f"{zone.strength:.1%}",
            }
            for zone in profile.gex_zones
        ]
        zone_table.update()

        status_label.set_text(
            f"CME loaded | {state.instrument.name}"
        )

    except Exception as exc:
        ui.notify(
            str(exc),
            type="negative",
        )


async def load_market_data():
    load_button.disable()
    status_label.set_text("Loading CME + Treasury...")

    try:
        state.select_instrument(
            instrument_select.value
        )

        state.series = series_select.value
        state.top_n = int(walls_select.value)

        await run.io_bound(state.load)

        expiration_select.options = list(
            state.expirations
        )
        expiration_select.value = (
            state.selected_expiration
        )
        expiration_select.update()

        if state.chain is not None:
            bulletin_label.set_text(
                f"Bulletin: "
                f"{state.chain.metadata.bulletin_date}"
            )

            option_rows_label.set_text(
                f"CME options: "
                f"{len(state.chain.points):,}"
            )

        await refresh_profile()

        ui.notify(
            "CME data loaded",
            type="positive",
        )

    except Exception as exc:
        status_label.set_text(
            f"Load failed: {exc}"
        )

        ui.notify(
            str(exc),
            type="negative",
        )

    finally:
        load_button.enable()


async def expiration_changed():
    if state.loaded:
        await refresh_profile()


async def walls_changed():
    if state.loaded:
        state.top_n = int(walls_select.value)
        await refresh_profile()


ui.page_title("CME Options Lab")

ui.add_css("""
body {
    background: #f5f7fa;
}

.kpi-card {
    min-height: 112px;
}

.section-title {
    font-size: 1.15rem;
    font-weight: 600;
}
""")


with ui.column().classes(
    "w-full max-w-screen-2xl mx-auto p-6 gap-5"
):

    with ui.row().classes(
        "w-full items-center justify-between"
    ):
        with ui.column().classes("gap-0"):
            ui.label(
                "CME OPTIONS LAB"
            ).classes(
                "text-3xl font-bold"
            )

            ui.label(
                "Futures • Options • Gamma • "
                "Vanna • Volatility Research"
            ).classes(
                "text-gray-500"
            )

        status_label = ui.label(
            "CME not loaded"
        ).classes(
            "text-sm font-medium"
        )

    with ui.card().classes("w-full"):
        with ui.row().classes(
            "w-full items-end gap-4"
        ):

            instrument_select = ui.select(
                options=INSTRUMENT_OPTIONS,
                value="live_cattle",
                label="Instrument",
            ).classes("w-64")

            expiration_select = ui.select(
                options=[],
                label="Expiration",
                on_change=expiration_changed,
            ).classes("w-44")

            walls_select = ui.select(
                options=WALL_OPTIONS,
                value=3,
                label="Walls",
                on_change=walls_changed,
            ).classes("w-28")

            series_select = ui.select(
                options=["STANDARD"],
                value="STANDARD",
                label="Series",
            ).classes("w-40")

            load_button = ui.button(
                "LOAD CME DATA",
                icon="download",
                on_click=load_market_data,
            )

        with ui.row().classes(
            "w-full gap-6 mt-2"
        ):
            bulletin_label = ui.label(
                "Bulletin: -"
            ).classes("text-gray-500")

            option_rows_label = ui.label(
                "CME options: -"
            ).classes("text-gray-500")

    with ui.tabs().classes("w-full") as tabs:
        overview_tab = ui.tab("OVERVIEW")
        gex_vex_tab = ui.tab("GEX / VEX")
        zones_tab = ui.tab("GEX ZONES")
        chain_tab = ui.tab("OPTIONS CHAIN")
        expirations_tab = ui.tab("EXPIRATIONS")
        volatility_tab = ui.tab("VOLATILITY")
        gap_tab = ui.tab("GAP / ROLL LAB")
        quality_tab = ui.tab("DATA QUALITY")

    with ui.tab_panels(
        tabs,
        value=overview_tab,
    ).classes("w-full bg-transparent"):

        with ui.tab_panel(overview_tab):

            with ui.grid(
                columns=5
            ).classes("w-full gap-4"):

                with ui.card().classes(
                    "kpi-card"
                ):
                    ui.label(
                        "FUTURES"
                    ).classes("text-gray-500")
                    futures_value = ui.label(
                        "-"
                    ).classes(
                        "text-2xl font-bold"
                    )

                with ui.card().classes(
                    "kpi-card"
                ):
                    ui.label(
                        "NET GEX"
                    ).classes("text-gray-500")
                    net_gex_value = ui.label(
                        "-"
                    ).classes(
                        "text-2xl font-bold"
                    )

                with ui.card().classes(
                    "kpi-card"
                ):
                    ui.label(
                        "NET VEX"
                    ).classes("text-gray-500")
                    net_vex_value = ui.label(
                        "-"
                    ).classes(
                        "text-2xl font-bold"
                    )

                with ui.card().classes(
                    "kpi-card"
                ):
                    ui.label(
                        "GEX ZONES"
                    ).classes("text-gray-500")
                    zones_value = ui.label(
                        "-"
                    ).classes(
                        "text-2xl font-bold"
                    )

                with ui.card().classes(
                    "kpi-card"
                ):
                    ui.label(
                        "IV COVERAGE"
                    ).classes("text-gray-500")
                    iv_value = ui.label(
                        "-"
                    ).classes(
                        "text-2xl font-bold"
                    )

            ui.label(
                "Price Position"
            ).classes(
                "section-title mt-6"
            )

            nearest_table = ui.table(
                columns=[
                    {
                        "name": "type",
                        "label": "Wall",
                        "field": "type",
                    },
                    {
                        "name": "side",
                        "label": "Position",
                        "field": "side",
                    },
                    {
                        "name": "strike",
                        "label": "Strike",
                        "field": "strike",
                    },
                    {
                        "name": "distance",
                        "label": "Distance",
                        "field": "distance",
                    },
                    {
                        "name": "distance_pct",
                        "label": "Distance %",
                        "field": "distance_pct",
                    },
                ],
                rows=[],
            ).classes("w-full")

            ui.label(
                "Dynamic GEX Zones"
            ).classes(
                "section-title mt-6"
            )

            zone_table = ui.table(
                columns=[
                    {
                        "name": "zone",
                        "label": "Zone",
                        "field": "zone",
                    },
                    {
                        "name": "peak",
                        "label": "Peak",
                        "field": "peak",
                    },
                    {
                        "name": "net_gex",
                        "label": "Net GEX",
                        "field": "net_gex",
                    },
                    {
                        "name": "peak_gex",
                        "label": "Peak GEX",
                        "field": "peak_gex",
                    },
                    {
                        "name": "strikes",
                        "label": "Strikes",
                        "field": "strikes",
                    },
                    {
                        "name": "strength",
                        "label": "Strength",
                        "field": "strength",
                    },
                ],
                rows=[],
            ).classes("w-full")

        with ui.tab_panel(gex_vex_tab):

            ui.label(
                "Gamma Walls"
            ).classes("text-2xl font-bold")

            with ui.grid(
                columns=2
            ).classes("w-full gap-4"):

                gamma_positive = make_wall_table(
                    "Positive Net GEX"
                )

                gamma_negative = make_wall_table(
                    "Negative Net GEX"
                )

            ui.label(
                "Vanna / VEX Walls"
            ).classes(
                "text-2xl font-bold mt-6"
            )

            with ui.grid(
                columns=2
            ).classes("w-full gap-4"):

                vanna_positive = make_wall_table(
                    "Positive Net VEX"
                )

                vanna_negative = make_wall_table(
                    "Negative Net VEX"
                )

        with ui.tab_panel(zones_tab):
            ui.label(
                "Dynamic GEX Zones"
            ).classes("text-2xl font-bold")

            ui.label(
                "Spatial GEX-zone research view "
                "will be expanded here."
            ).classes("text-gray-500")

        with ui.tab_panel(chain_tab):
            ui.label(
                "Options Chain"
            ).classes("text-2xl font-bold")

            ui.label(
                "Normalized CME option-chain "
                "viewer is the next stage."
            )

        with ui.tab_panel(expirations_tab):
            ui.label(
                "Expiration Matrix"
            ).classes("text-2xl font-bold")

            ui.label(
                "Cross-expiration GEX / VEX / "
                "OI matrix will live here."
            )

        with ui.tab_panel(volatility_tab):
            ui.label(
                "Volatility Lab"
            ).classes("text-2xl font-bold")

            ui.label(
                "IV and multi-timeframe realized "
                "volatility research."
            )

        with ui.tab_panel(gap_tab):
            ui.label(
                "Gap / Roll Lab"
            ).classes("text-2xl font-bold")

            ui.label(
                "Gap closure and contract-roll "
                "research module."
            )

        with ui.tab_panel(quality_tab):

            ui.label(
                "Data Quality"
            ).classes("text-2xl font-bold")

            with ui.grid(
                columns=2
            ).classes("max-w-xl gap-4"):

                with ui.card():
                    ui.label(
                        "Selected expiration"
                    ).classes("text-gray-500")

                    expiration_value = ui.label(
                        "-"
                    ).classes(
                        "text-xl font-bold"
                    )

                with ui.card():
                    ui.label(
                        "Exposure rows"
                    ).classes("text-gray-500")

                    data_rows_value = ui.label(
                        "-"
                    ).classes(
                        "text-xl font-bold"
                    )


ui.run(
    title="CME Options Lab",
    reload=False,
)