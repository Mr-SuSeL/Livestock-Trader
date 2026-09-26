from dataclasses import dataclass

from config import INSTRUMENTS, InstrumentConfig

from collectors.cme_options import (
    CMEOptionsChain,
    collect_options_chain,
)
from collectors.treasury_rates import (
    TreasuryCurve,
    collect_treasury_curve,
)

from analysis.options_flow import (
    OptionExposure,
    TraderProfile,
    available_expirations,
    build_option_exposures,
    build_trader_profile,
)


@dataclass(slots=True)
class DashboardState:
    instrument_key: str = "live_cattle"
    series: str = "STANDARD"
    top_n: int = 3

    chain: CMEOptionsChain | None = None
    curve: TreasuryCurve | None = None
    exposures: tuple[OptionExposure, ...] = ()

    expirations: tuple[str, ...] = ()
    selected_expiration: str | None = None

    @property
    def instrument(self) -> InstrumentConfig:
        return INSTRUMENTS[self.instrument_key]

    @property
    def loaded(self) -> bool:
        return (
            self.chain is not None
            and self.curve is not None
            and bool(self.exposures)
        )

    def load(self) -> None:
        """
        Download and calculate a fresh dataset.

        This is the expensive operation.
        """
        instrument = self.instrument

        chain = collect_options_chain(instrument)

        curve = collect_treasury_curve(
            chain.metadata.bulletin_date
        )

        exposures = build_option_exposures(
            chain=chain,
            instrument=instrument,
            curve=curve,
            series=self.series,
        )

        expirations = available_expirations(chain)

        self.chain = chain
        self.curve = curve
        self.exposures = exposures
        self.expirations = expirations

        if self.selected_expiration not in expirations:
            self.selected_expiration = (
                expirations[0]
                if expirations
                else None
            )

    def select_instrument(
        self,
        instrument_key: str,
    ) -> None:
        if instrument_key not in INSTRUMENTS:
            raise KeyError(
                f"Unknown instrument: {instrument_key}"
            )

        if instrument_key == self.instrument_key:
            return

        self.instrument_key = instrument_key

        self.chain = None
        self.curve = None
        self.exposures = ()
        self.expirations = ()
        self.selected_expiration = None

    def select_expiration(
        self,
        expiration_code: str,
    ) -> None:
        if expiration_code not in self.expirations:
            raise ValueError(
                f"Expiration {expiration_code!r} "
                "is not available."
            )

        self.selected_expiration = expiration_code

    def build_profile(self) -> TraderProfile:
        """
        Build a profile from already loaded exposures.

        No CME or Treasury download happens here.
        """
        if not self.loaded:
            raise RuntimeError(
                "Dashboard data has not been loaded."
            )

        if self.selected_expiration is None:
            raise RuntimeError(
                "No expiration selected."
            )

        return build_trader_profile(
            exposures=self.exposures,
            expiration_code=self.selected_expiration,
            top_n=self.top_n,
        )