"""
Command-line entry point for the futures/options analytics platform.

Examples
--------
List configured instruments:

    python main.py list

Show one instrument:

    python main.py show lean_hogs

Probe one market-data source:

    python main.py probe lean_hogs stooq

The CLI deliberately separates:

    instrument configuration
            |
            v
        data source
            |
            v
         collector

Collectors therefore do not need to know what Lean Hogs,
Live Cattle or any future market actually is.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from config import (
    DEFAULT_INSTRUMENT,
    INSTRUMENTS,
    InstrumentConfig,
    get_instrument,
)


def build_parser() -> argparse.ArgumentParser:
    """
    Build the command-line argument parser.
    """

    parser = argparse.ArgumentParser(
        prog="market-lab",
        description=(
            "Futures and options market-data analytics platform."
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
        help="Show configuration for one instrument.",
    )

    show_parser.add_argument(
        "instrument",
        nargs="?",
        default=DEFAULT_INSTRUMENT,
        help=(
            "Internal instrument key, "
            f"default: {DEFAULT_INSTRUMENT}"
        ),
    )

    probe_parser = subparsers.add_parser(
        "probe",
        help="Probe a market-data source.",
    )

    probe_parser.add_argument(
        "instrument",
        help="Internal instrument key.",
    )

    probe_parser.add_argument(
        "source",
        help="Market-data source, e.g. stooq.",
    )

    return parser


def print_instrument_list() -> None:
    """
    Print all instruments configured in config.py.
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
    Print configuration of one instrument.
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

    if not instrument.source_symbols:
        print("  none")
        return

    for source, symbol in sorted(
        instrument.source_symbols.items()
    ):
        print(f"  {source:<12} {symbol}")


def probe_stooq(
    instrument: InstrumentConfig,
) -> int:
    """
    Probe Stooq using the symbol defined in InstrumentConfig.
    """

    from collectors.stooq import probe

    symbol = instrument.symbol_for("STOOQ")

    if symbol is None:
        print(
            f"No STOOQ symbol configured "
            f"for {instrument.name}."
        )
        return 2

    probe(symbol)

    return 0


def probe_source(
    instrument_key: str,
    source: str,
) -> int:
    """
    Dispatch a probe to the selected source.

    New collectors will be registered here as we implement them.
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

    print(
        "ERROR: Unsupported probe source: "
        f"{normalized_source}"
    )

    print(
        "Currently implemented probe sources: "
        "STOOQ"
    )

    return 2


def run(
    argv: Sequence[str] | None = None,
) -> int:
    """
    Execute CLI command and return a process exit code.
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

    parser.error(
        f"Unsupported command: {args.command}"
    )

    return 2


def main() -> None:
    """
    Application entry point.
    """

    exit_code = run()

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()