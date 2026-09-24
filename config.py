"""
Application configuration for the futures/options analytics platform.

Instrument definitions belong here, not inside data collectors.

Collectors should be generic:
    source -> raw/normalized market data

Instrument configuration defines:
    what market we want to analyse
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class InstrumentConfig:
    """
    Configuration describing one futures market.

    Symbols are stored per data provider because different providers
    may use different identifiers for the same underlying market.
    """

    name: str

    exchange: str
    currency: str

    futures_root: str

    contract_size: float
    point_value: float

    price_unit: str

    source_symbols: Mapping[str, str] = field(
        default_factory=dict
    )

    def symbol_for(
        self,
        source: str,
    ) -> str | None:
        """
        Return symbol/root used by a specific provider.
        """

        return self.source_symbols.get(
            source.strip().upper()
        )


INSTRUMENTS: dict[str, InstrumentConfig] = {
    "lean_hogs": InstrumentConfig(
        name="Lean Hogs",
        exchange="CME",
        currency="USD",
        futures_root="HE",
        contract_size=40_000.0,
        point_value=400.0,
        price_unit="US cents per pound",
        source_symbols={
            "CME": "HE",
            "STOOQ": "HE.F",
            "YAHOO": "HE=F",
        },
    ),
}


DEFAULT_INSTRUMENT = "lean_hogs"


def get_instrument(
    key: str = DEFAULT_INSTRUMENT,
) -> InstrumentConfig:
    """
    Return instrument configuration by internal key.
    """

    normalized = key.strip().lower()

    try:
        return INSTRUMENTS[normalized]

    except KeyError as exc:
        available = ", ".join(
            sorted(INSTRUMENTS)
        )

        raise KeyError(
            f"Unknown instrument: {key!r}. "
            f"Available instruments: {available}"
        ) from exc
