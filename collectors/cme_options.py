"""
CME futures-options collector.

The collector reads CME Daily Bulletin option reports and converts
their extracted text into normalized option-contract records.

The initial parser intentionally handles only fields whose layout
has been verified against the CME livestock bulletins.
"""

from __future__ import annotations

import re

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

import requests
from pypdf import PdfReader

from config import InstrumentConfig


SOURCE_NAME = "CME"

BASE_URL = (
    "https://www.cmegroup.com/"
    "daily_bulletin/current"
)


class CMEOptionsError(RuntimeError):
    """Base exception for CME options collection errors."""


@dataclass(frozen=True, slots=True)
class CMEOptionPoint:
    """
    One parsed CME futures-option strike.
    """

    expiration_code: str
    option_type: str

    strike_raw: int
    strike: float

    futures_settlement: float | None


@dataclass(frozen=True, slots=True)
class BulletinFiles:
    """
    CME Daily Bulletin files for one instrument.
    """

    calls: str
    puts: str


BULLETIN_FILES: dict[str, BulletinFiles] = {
    "HE": BulletinFiles(
        calls="Section19_Lean_Hogs_Call_Options.pdf",
        puts="Section20_Lean_Hogs_Put_Options.pdf",
    ),
    "LE": BulletinFiles(
        calls="Section15_Live_Cattle_Call_Options.pdf",
        puts="Section16_Live_Cattle_Put_Options.pdf",
    ),
}


SECTION_PATTERN = re.compile(
    r"\("
    r"FUTURES\s+SETT\.\s*"
    r"(?P<settlement>\d+(?:\.\d+)?)"
    r".*?"
    r"\)"
    r"(?P<expiration>[A-Z]{3}\d{2})"
)


STRIKE_PATTERN = re.compile(
    r"(?P<strike>\d+)\s*$"
)


def _bulletin_url(
    filename: str,
) -> str:
    """
    Build the current CME Daily Bulletin URL.
    """

    return (
        f"{BASE_URL}/{filename}"
    )


def _download_pdf(
    filename: str,
    timeout: float = 30.0,
) -> bytes:
    """
    Download one CME Daily Bulletin PDF.
    """

    url = _bulletin_url(
        filename
    )

    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 market-data-research"
                )
            },
        )

        response.raise_for_status()

    except requests.RequestException as exc:
        raise CMEOptionsError(
            f"CME request failed: {exc}"
        ) from exc

    content = response.content

    if not content.startswith(b"%PDF"):
        raise CMEOptionsError(
            "CME response is not a PDF."
        )

    return content


def _extract_text(
    pdf_bytes: bytes,
) -> str:
    """
    Extract text from one CME bulletin.
    """

    try:
        reader = PdfReader(
            BytesIO(pdf_bytes)
        )

        pages: list[str] = []

        for page in reader.pages:
            text = page.extract_text()

            if text:
                pages.append(
                    text
                )

    except Exception as exc:
        raise CMEOptionsError(
            f"Unable to parse CME PDF: {exc}"
        ) from exc

    result = "\n".join(
        pages
    ).strip()

    if not result:
        raise CMEOptionsError(
            "No text extracted from CME PDF."
        )

    return result


def _parse_option_text(
    text: str,
    option_type: str,
    strike_scale: float,
) -> list[CMEOptionPoint]:
    """
    Parse expiration, underlying settlement and strikes.

    Open interest, volume and option settlement are deliberately
    excluded from this first parser version.
    """

    if strike_scale <= 0:
        raise ValueError(
            "strike_scale must be greater than zero."
        )

    normalized_type = (
        option_type
        .strip()
        .upper()
    )

    if normalized_type not in {
        "CALL",
        "PUT",
    }:
        raise ValueError(
            "option_type must be CALL or PUT."
        )

    points: list[CMEOptionPoint] = []

    current_expiration: str | None = None
    current_futures_settlement: float | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        section_match = (
            SECTION_PATTERN.search(
                line
            )
        )

        if section_match:

            current_expiration = (
                section_match.group(
                    "expiration"
                )
            )

            current_futures_settlement = float(
                section_match.group(
                    "settlement"
                )
            )

            continue

        if current_expiration is None:
            continue

        if line.startswith(
            "TOTAL"
        ):
            current_expiration = None
            current_futures_settlement = None
            continue

        strike_match = STRIKE_PATTERN.search(
            line
        )

        if strike_match is None:
            continue

        strike_raw = int(
            strike_match.group(
                "strike"
            )
        )

        strike = (
            strike_raw
            / strike_scale
        )

        points.append(
            CMEOptionPoint(
                expiration_code=(
                    current_expiration
                ),
                option_type=(
                    normalized_type
                ),
                strike_raw=(
                    strike_raw
                ),
                strike=strike,
                futures_settlement=(
                    current_futures_settlement
                ),
            )
        )

    return points


def _files_for_instrument(
    instrument: InstrumentConfig,
) -> BulletinFiles:
    """
    Resolve CME bulletin filenames from instrument metadata.
    """

    root = (
        instrument.futures_root
        .strip()
        .upper()
    )

    try:
        return BULLETIN_FILES[
            root
        ]

    except KeyError as exc:
        raise CMEOptionsError(
            "No CME options bulletin configured "
            f"for futures root {root!r}."
        ) from exc


def collect_options(
    instrument: InstrumentConfig,
) -> tuple[CMEOptionPoint, ...]:
    """
    Collect currently published CME option strikes.
    """

    files = _files_for_instrument(
        instrument
    )

    call_text = _extract_text(
        _download_pdf(
            files.calls
        )
    )

    put_text = _extract_text(
        _download_pdf(
            files.puts
        )
    )

    calls = _parse_option_text(
        text=call_text,
        option_type="CALL",
        strike_scale=(
            instrument.option_strike_scale
        ),
    )

    puts = _parse_option_text(
        text=put_text,
        option_type="PUT",
        strike_scale=(
            instrument.option_strike_scale
        ),
    )

    points = (
        calls
        + puts
    )

    if not points:
        raise CMEOptionsError(
            "No CME option strikes parsed."
        )

    return tuple(
        points
    )


def print_options_sample(
    points: tuple[CMEOptionPoint, ...],
    limit: int = 20,
) -> None:
    """
    Print a small sample of parsed option strikes.
    """

    print("=" * 78)
    print("CME OPTIONS PARSER")
    print("=" * 78)

    print(
        f"{'Expiration':<12}"
        f"{'Type':<8}"
        f"{'Strike':>12}"
        f"{'Raw':>10}"
        f"{'Fut Settle':>14}"
    )

    print("-" * 78)

    for point in points[:limit]:

        if point.futures_settlement is None:
            futures_text = "-"
        else:
            futures_text = (
                f"{point.futures_settlement:.3f}"
            )

        print(
            f"{point.expiration_code:<12}"
            f"{point.option_type:<8}"
            f"{point.strike:>12.3f}"
            f"{point.strike_raw:>10}"
            f"{futures_text:>14}"
        )

    print()
    print(
        f"Parsed records: {len(points):,}"
    )

