"""
Command-line entry point for the futures/options analytics platform.

Examples
--------
List instruments:

    python main.py list

Show configuration:

    python main.py show lean_hogs

Probe Yahoo:

    python main.py probe lean_hogs yahoo

Probe Stooq:

    python main.py probe lean_hogs stooq

Probe CFTC positioning:

    python main.py probe lean_hogs cftc

The CLI separates:

    instrument configuration
            |
            v
        data source
            |
            v
         collector
"""

from __future__ import annotations

import argparse
from typing import Sequence

from config import (
    DEFAULT_INSTRUMENT,
    INSTRUMENTS,
    InstrumentConfig,
    get_instrument,
)


SUPPORTED_PROBE_SOURCES = (
    "STOOQ",
    "YAHOO",
    "CFTC",
)


def build_parser() -> argparse.ArgumentParser:
    """
    Build command-line parser.
    """

    parser = argparse.ArgumentParser(
        prog="market-lab",
        description=(
            "Futures and options market-data "
            "analytics platform."
        ),
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    subparsers.add_parser(
        "list",
        help="List configured instruments.",
    )

    show_parser = subparsers.add_parser(
        "show",
        help="Show instrument configuration.",
    )

    show_parser.add_argument(
        "instrument",
        nargs="?",
        default=DEFAULT_INSTRUMENT,
    )

    probe_parser = subparsers.add_parser(
        "probe",
        help="Probe a market-data source.",
    )

    probe_parser.add_argument(
        "instrument",
    )

    probe_parser.add_argument(
        "source",
    )

    return parser


def print_instrument_list() -> None:
    """
    Print configured instruments.
    """

    print("=" * 70)
    print("CONFIGURED INSTRUMENTS")
    print("=" * 70)

    if not INSTRUMENTS:
        print("No instruments configured.")
        return

    for key, instrument in sorted(
        INSTRUMENTS.items()
    ):
        print(
            f"{key:<20} "
            f"{instrument.name:<25} "
            f"{instrument.exchange:<10} "
            f"{instrument.futures_root}"
        )


def print_instrument(
    key: str,
    instrument: InstrumentConfig,
) -> None:
    """
    Print one instrument configuration.
    """

    print("=" * 70)
    print("INSTRUMENT CONFIGURATION")
    print("=" * 70)

    print(f"Key:           {key}")
    print(f"Name:          {instrument.name}")
    print(f"Exchange:      {instrument.exchange}")
    print(f"Currency:      {instrument.currency}")
    print(f"Futures root:  {instrument.futures_root}")
    print(f"Contract size: {instrument.contract_size}")
    print(f"Point value:   {instrument.point_value}")
    print(f"Price unit:    {instrument.price_unit}")

    print()
    print("Provider symbols:")

    if instrument.source_symbols:

        for source, symbol in sorted(
            instrument.source_symbols.items()
        ):
            print(
                f"  {source:<12} {symbol}"
            )

    else:
        print("  none")

    print()
    print("Provider IDs:")

    if instrument.source_ids:

        for source, source_id in sorted(
            instrument.source_ids.items()
        ):
            print(
                f"  {source:<12} {source_id}"
            )

    else:
        print("  none")


def probe_stooq(
    instrument: InstrumentConfig,
) -> int:
    """
    Probe Stooq.
    """

    from collectors.stooq import probe

    symbol = instrument.symbol_for(
        "STOOQ"
    )

    if symbol is None:
        print(
            f"No STOOQ symbol configured "
            f"for {instrument.name}."
        )
        return 2

    probe(symbol)

    return 0


def probe_yahoo(
    instrument: InstrumentConfig,
) -> int:
    """
    Probe Yahoo Finance.
    """

    from collectors.yahoo_futures import probe

    symbol = instrument.symbol_for(
        "YAHOO"
    )

    if symbol is None:
        print(
            f"No YAHOO symbol configured "
            f"for {instrument.name}."
        )
        return 2

    success = probe(symbol)

    return 0 if success else 1


def probe_cftc(
    instrument: InstrumentConfig,
) -> int:
    """
    Retrieve recent CFTC positioning observations.
    """

    from collectors.cftc import (
        CFTCError,
        add_positioning_metrics,
        collect_by_market_code,
    )

    market_code = instrument.id_for(
        "CFTC"
    )

    if market_code is None:
        print(
            f"No CFTC market identifier configured "
            f"for {instrument.name}."
        )
        return 2

    print("=" * 70)
    print("CFTC POSITIONING PROBE")
    print("=" * 70)

    print(f"Instrument:  {instrument.name}")
    print(f"Market code: {market_code}")
    print()

    try:
        dataset = collect_by_market_code(
            market_code=market_code,
            limit=10,
        )

    except CFTCError as exc:
        print("Status: FAILED")
        print(f"Reason: {exc}")
        return 1

    dataframe = add_positioning_metrics(
        dataset.dataframe
    )

    if dataframe.empty:
        print("Status: FAILED")
        print("Reason: No normalized CFTC rows.")
        return 1

    print("Status: OK")
    print(f"Rows:   {len(dataframe)}")
    print()

    latest = dataframe.iloc[-1]

    print("LATEST REPORT")
    print("-" * 70)

    print(
        f"Report date: "
        f"{latest['report_date']}"
    )

    print(
        f"Market: "
        f"{latest['market_and_exchange']}"
    )

    print(
        f"Commodity: "
        f"{latest['commodity_name']}"
    )

    print(
        f"Open interest: "
        f"{latest['open_interest']:,.0f}"
    )

    metric_labels = {
        "producer_long": "Producer long",
        "producer_short": "Producer short",
        "producer_net": "Producer net",
        "swap_long": "Swap long",
        "swap_short": "Swap short",
        "swap_net": "Swap net",
        "managed_money_long": "Managed Money long",
        "managed_money_short": "Managed Money short",
        "managed_money_net": "Managed Money net",
        "other_reportable_long": "Other Reportable long",
        "other_reportable_short": "Other Reportable short",
        "other_reportable_net": "Other Reportable net",
    }

    print()

    for column, label in metric_labels.items():

        if column not in latest.index:
            continue

        value = latest[column]

        if value != value:
            continue

        print(
            f"{label:<24} "
            f"{value:>12,.0f}"
        )

    print()
    print(
        f"Retrieved at: "
        f"{dataset.retrieved_at.isoformat()}"
    )

    return 0


def probe_source(
    instrument_key: str,
    source: str,
) -> int:
    """
    Route probe request to a selected collector.
    """

    try:
        instrument = get_instrument(
            instrument_key
        )

    except KeyError as exc:
        print(f"ERROR: {exc}")
        return 2

    normalized_source = (
        source.strip().upper()
    )

    print(
        f"Instrument: {instrument.name}"
    )

    print(
        f"Data source: {normalized_source}"
    )

    print()

    if normalized_source == "STOOQ":
        return probe_stooq(
            instrument
        )

    if normalized_source == "YAHOO":
        return probe_yahoo(
            instrument
        )

    if normalized_source == "CFTC":
        return probe_cftc(
            instrument
        )

    available = ", ".join(
        SUPPORTED_PROBE_SOURCES
    )

    print(
        f"ERROR: Unsupported source: "
        f"{normalized_source}"
    )

    print(
        f"Supported probe sources: "
        f"{available}"
    )

    return 2


def run(
    argv: Sequence[str] | None = None,
) -> int:
    """
    Execute CLI command.
    """

    parser = build_parser()

    args = parser.parse_args(
        argv
    )

    if args.command == "list":
        print_instrument_list()
        return 0

    if args.command == "show":

        try:
            instrument = get_instrument(
                args.instrument
            )

        except KeyError as exc:
            print(f"ERROR: {exc}")
            return 2

        print_instrument(
            args.instrument,
            instrument,
        )

        return 0

    if args.command == "probe":
        return probe_source(
            instrument_key=args.instrument,
            source=args.source,
        )

    return 2


def main() -> None:
    """
    Application entry point.
    """

    raise SystemExit(
        run()
    )


if __name__ == "__main__":
    main()