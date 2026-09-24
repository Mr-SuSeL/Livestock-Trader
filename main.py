"""
Command-line entry point for the futures/options analytics platform.
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

    for source, symbol in sorted(
        instrument.source_symbols.items()
    ):
        print(
            f"  {source:<12} {symbol}"
        )


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


def probe_source(
    instrument_key: str,
    source: str,
) -> int:
    """
    Route probe request.
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
        return probe_stooq(instrument)

    if normalized_source == "YAHOO":
        return probe_yahoo(instrument)

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
    Execute CLI.
    """

    parser = build_parser()

    args = parser.parse_args(argv)

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