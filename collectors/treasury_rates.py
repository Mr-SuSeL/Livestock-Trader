"""
U.S. Treasury yield-curve collector.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import urllib.request
import xml.etree.ElementTree as ET


TREASURY_URL = (
    "https://home.treasury.gov/"
    "resource-center/data-chart-center/"
    "interest-rates/pages/xml"
)

NAMESPACES = {
    "a": "http://www.w3.org/2005/Atom",
    "m": (
        "http://schemas.microsoft.com/"
        "ado/2007/08/dataservices/metadata"
    ),
}


class TreasuryRatesError(RuntimeError):
    """
    Raised when Treasury yield-curve data cannot be obtained.
    """


@dataclass(frozen=True, slots=True)
class TreasuryRate:
    """
    One point on the Treasury yield curve.
    """

    maturity_years: float
    rate: float


@dataclass(frozen=True, slots=True)
class TreasuryCurve:
    """
    Treasury yield curve for one observation date.
    """

    curve_date: date
    rates: tuple[TreasuryRate, ...]


TENORS = (
    ("BC_1MONTH", 1.0 / 12.0),
    ("BC_1_5MONTH", 1.5 / 12.0),
    ("BC_2MONTH", 2.0 / 12.0),
    ("BC_3MONTH", 3.0 / 12.0),
    ("BC_4MONTH", 4.0 / 12.0),
    ("BC_6MONTH", 6.0 / 12.0),
    ("BC_1YEAR", 1.0),
)


def _download_curve_xml(
    year: int,
) -> bytes:
    """
    Download Treasury yield-curve XML for one year.
    """

    url = (
        f"{TREASURY_URL}"
        "?data=daily_treasury_yield_curve"
        f"&field_tdr_date_value={year}"
    )

    try:
        with urllib.request.urlopen(
            url,
            timeout=30,
        ) as response:
            return response.read()

    except Exception as exc:
        raise TreasuryRatesError(
            "Unable to download Treasury yield curve."
        ) from exc


def _parse_curve(
    xml_data: bytes,
    target_date: date,
) -> TreasuryCurve:
    """
    Parse the Treasury curve for an exact date.
    """

    root = ET.fromstring(xml_data)

    for entry in root.findall(
        "a:entry",
        NAMESPACES,
    ):
        properties = entry.find(
            "a:content/m:properties",
            NAMESPACES,
        )

        if properties is None:
            continue

        values = {
            element.tag.split("}")[-1]:
                element.text
            for element in properties
        }

        date_text = values.get("NEW_DATE")

        if not date_text:
            continue

        curve_date = datetime.fromisoformat(
            date_text
        ).date()

        if curve_date != target_date:
            continue

        rates: list[TreasuryRate] = []

        for field_name, maturity_years in TENORS:
            rate_text = values.get(field_name)

            if not rate_text:
                continue

            rates.append(
                TreasuryRate(
                    maturity_years=maturity_years,
                    rate=float(rate_text) / 100.0,
                )
            )

        if not rates:
            raise TreasuryRatesError(
                "Treasury curve contains no usable rates."
            )

        return TreasuryCurve(
            curve_date=curve_date,
            rates=tuple(rates),
        )

    raise TreasuryRatesError(
        f"No Treasury curve found for {target_date}."
    )


def collect_treasury_curve(
    target_date: date,
) -> TreasuryCurve:
    """
    Collect the Treasury yield curve for an exact date.
    """

    xml_data = _download_curve_xml(
        target_date.year
    )

    return _parse_curve(
        xml_data=xml_data,
        target_date=target_date,
    )

def rate_for_maturity(
    curve: TreasuryCurve,
    maturity_years: float,
) -> float:
    """
    Return an approximate Treasury rate for maturity in years.

    Rates between published tenors are linearly interpolated.
    Maturities outside the available range use the nearest tenor.
    """

    if maturity_years <= 0:
        raise ValueError(
            "Maturity must be greater than zero."
        )

    rates = curve.rates

    if not rates:
        raise TreasuryRatesError(
            "Treasury curve contains no rates."
        )

    if maturity_years <= rates[0].maturity_years:
        return rates[0].rate

    if maturity_years >= rates[-1].maturity_years:
        return rates[-1].rate

    for left, right in zip(
        rates,
        rates[1:],
    ):
        if (
            left.maturity_years
            <= maturity_years
            <= right.maturity_years
        ):
            weight = (
                maturity_years
                - left.maturity_years
            ) / (
                right.maturity_years
                - left.maturity_years
            )

            return (
                left.rate
                + weight
                * (right.rate - left.rate)
            )

    raise TreasuryRatesError(
        "Unable to interpolate Treasury rate."
    )


def rate_for_maturity(
    curve: TreasuryCurve,
    maturity_years: float,
) -> float:
    """
    Return the Treasury rate for a given maturity.

    Linear interpolation is used between available tenors.
    The nearest available tenor is used outside the curve range.
    """

    if maturity_years <= 0:
        raise ValueError(
            "Maturity must be greater than zero."
        )

    rates = curve.rates

    if not rates:
        raise TreasuryRatesError(
            "Treasury curve contains no rates."
        )

    if maturity_years <= rates[0].maturity_years:
        return rates[0].rate

    if maturity_years >= rates[-1].maturity_years:
        return rates[-1].rate

    for left, right in zip(rates, rates[1:]):
        if (
            left.maturity_years
            <= maturity_years
            <= right.maturity_years
        ):
            weight = (
                maturity_years - left.maturity_years
            ) / (
                right.maturity_years
                - left.maturity_years
            )

            return (
                left.rate
                + weight
                * (right.rate - left.rate)
            )

    raise TreasuryRatesError(
        "Unable to interpolate Treasury rate."
    )