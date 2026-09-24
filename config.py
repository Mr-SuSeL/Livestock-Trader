"""
Application configuration for the futures/options analytics platform.

Instrument definitions belong here, not inside data collectors
or analysis modules.

Collectors should be generic:
    source -> raw/normalized market data

Analysis modules should use instrument metadata from this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class InstrumentConfig:
    """
    Configuration describing one futures market.

    Provider symbols and external identifiers are stored here because
    different data sources use different identifiers for the same
    underlying market.

    Contract months are exchange/instrument metadata and therefore
    also belong in configuration rather than analysis code.
    """

    name: str

    exchange: str
    currency: str

    futures_root: str

    contract_size: float
    point_value: float

    price_unit: str

    contract_months: tuple[int, ...]

    source_symbols: Mapping[str, str] = field(
        default_factory=dict
    )

    source_ids: Mapping[str, str] = field(
        default_factory=dict
    )

    def symbol_for(
        self,
        source: str,
    ) -> str | None:
        """
        Return the trading symbol used by a data provider.
        """

        return self.source_symbols.get(
            source.strip().upper()
        )

    def id_for(
        self,
        source: str,
    ) -> str | None:
        """
        Return a stable external identifier used by a provider.
        """

        return self.source_ids.get(
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
        contract_months=(
            2,
            4,
            5,
            6,
            7,
            8,
            10,
            12,
        ),
        source_symbols={
            "CME": "HE",
            "STOOQ": "HE.F",
            "YAHOO": "HE=F",
        },
        source_ids={
            "CFTC": "054642",
        },
    ),

    "live_cattle": InstrumentConfig(
        name="Live Cattle",
        exchange="CME",
        currency="USD",
        futures_root="LE",
        contract_size=40_000.0,
        point_value=400.0,
        price_unit="US cents per pound",
        contract_months=(
            2,
            4,
            6,
            8,
            10,
            12,
        ),
        source_symbols={
            "CME": "LE",
            "YAHOO": "LE=F",
        },
        source_ids={
            "CFTC": "057642",
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