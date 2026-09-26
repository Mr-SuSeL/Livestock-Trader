"""
CME futures-options collector.

The collector reads CME Daily Bulletin option reports and converts
their extracted text into normalized option-contract records.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, datetime
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

    series: str

    expiration_code: str
    option_type: str

    strike_raw: int
    strike: float

    futures_settlement: float | None
    option_settlement: float | None
    delta: float | None

    volume: int
    open_interest: int


@dataclass(frozen=True, slots=True)
class BulletinFiles:
    """
    CME Daily Bulletin files for one instrument.
    """

    calls: str
    puts: str


@dataclass(frozen=True, slots=True)
class BulletinMetadata:
    """
    Metadata extracted from one CME options bulletin.
    """

    bulletin_date: date
    option_expirations: dict[str, date]


@dataclass(frozen=True, slots=True)
class CMEOptionsChain:
    """
    Parsed CME options chain with bulletin metadata.
    """

    points: tuple[CMEOptionPoint, ...]
    metadata: BulletinMetadata


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

BULLETIN_DATE_PATTERN = re.compile(
    r"""
    \b
    (?P<weekday>Mon|Tue|Wed|Thu|Fri|Sat|Sun),
    \s+
    (?P<month>[A-Z][a-z]{2})
    \s+
    (?P<day>\d{1,2}),
    \s+
    (?P<year>\d{4})
    \b
    """,
    re.VERBOSE,
)

SECTION_HEADER_PATTERN = re.compile(
    r"""
    ^
    (?P<series_label>.*?)?
    \(?
    FUTURES\s+SETT\.
    \s*
    (?P<settlement>(?:\d+(?:\.\d+)?|\.\d+))
    .*?
    \)?
    \s*
    (?P<expiration>[A-Z]{3}\d{2})
    $
    """,
    re.VERBOSE,
)

ROW_TAIL_PATTERN = re.compile(
    r"""
    (?P<delta>\.\d{3}|1\.000)
    \s+
    (?:
        ----
        (?P<strike>\d+)
        |
        (?P<exercises>\d{1,3})
        (?P<exercise_strike>\d{3})
    )
    $
    """,
    re.VERBOSE,
)

# nie wiem czy to potzrebny regex czy nie...
OPTION_SETTLEMENT_PATTERN = re.compile(
    r"""
    ^.*?
    ----
    \s+
    (?P<settlement>
        \d+(?:\.\d+)?
        |
        \.\d+
        |
        CAB
    )
    \s+
    (?:
        [+-]
        |
        \d+
        |
        ----
    )
    """,
    re.VERBOSE,
)

NEW_ROW_PATTERN = re.compile(
    r"""
    ^.*?
    \s[+-]\s
    (?P<volume>\d+)
    \s+
    (?P<open_interest>----)
    (?P<change>\+?NEW)
    \s+
    (?P<trades>\d+|UNCH)
    .*?
    (?:
        ----
        (?P<strike>\d+)
        |
        (?P<exercises>\d{1,3})
        (?P<exercise_strike>\d{3})
    )
    $
    """,
    re.VERBOSE,
)


ACTIVE_ROW_PATTERN = re.compile(
    r"""
    ^.*?
    \s[+-]\s
    (?P<volume>\d+|----)
    \s+
    (?P<open_interest>\d+)
    \s+
    (?P<change>[+-]?\d+|\+?NEW|UNCH|-----)
    \s+
    (?P<trades>\d+|UNCH)
    .*?
    (?:
        ----
        (?P<strike>\d+)
        |
        (?P<exercises>\d{1,3})
        (?P<exercise_strike>\d{3})
    )
    $
    """,
    re.VERBOSE,
)

CAB_ROW_PATTERN = re.compile(
    r"""
    ^.*?
    \sCAB
    \s+
    (?P<volume>\d+|----)
    \s+
    (?P<open_interest>\d+)
    \s+
    (?P<change>[+-]?\d+|UNCH|[+-]?----|-----)
    \s+
    (?P<trades>\d+|UNCH)
    .*?
    (?:
        ----
        (?P<strike>\d+)
        |
        (?P<exercises>\d{1,3})
        (?P<exercise_strike>\d{3})
    )
    $
    """,
    re.VERBOSE,
)

SIGNED_UNCH_ROW_PATTERN = re.compile(
    r"""
    ^.*?
    \s
    (?P<volume>\d+|----)
    \s+
    (?P<open_interest>\d+)
    \s+
    (?P<change>[+-]UNCH)
    \s+
    (?P<trades>\d+|UNCH)
    .*?
    (?:
        ----
        (?P<strike>\d+)
        |
        (?P<exercises>\d{1,3})
        (?P<exercise_strike>\d{3})
    )
    $
    """,
    re.VERBOSE,
)

NO_CHANGE_ROW_PATTERN = re.compile(
    r"""
    ^.*?
    \s
    (?P<volume>\d+|----)
    \s+
    (?P<open_interest>\d+)
    \s+
    (?P<change>UNCH)
    \s+
    (?P<trades>UNCH)
    .*?
    (?:
        ----
        (?P<strike>\d+)
        |
        (?P<exercises>\d{1,3})
        (?P<exercise_strike>\d{3})
    )
    $
    """,
    re.VERBOSE,
)

TOTAL_PATTERN = re.compile(
    r"""
    ^TOTAL
    \s+
    (?P<volume>\d+)
    \s+
    (?P<open_interest>\d+)
    """,
    re.VERBOSE,
)

def _bulletin_url(
    filename: str,
) -> str:
    """
    Build the current CME Daily Bulletin URL.
    """

    return f"{BASE_URL}/{filename}"


def _download_pdf(
    filename: str,
    timeout: float = 30.0,
) -> bytes:
    """
    Download one CME Daily Bulletin PDF.
    """

    url = _bulletin_url(filename)

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
        reader = PdfReader(BytesIO(pdf_bytes))
        pages: list[str] = []

        for page in reader.pages:
            text = page.extract_text()

            if text:
                pages.append(text)

    except Exception as exc:
        raise CMEOptionsError(
            f"Unable to parse CME PDF: {exc}"
        ) from exc

    result = "\n".join(pages).strip()

    if not result:
        raise CMEOptionsError(
            "No text extracted from CME PDF."
        )

    return result


def _parse_bulletin_metadata(
    text: str,
) -> BulletinMetadata:
    """
    Parse bulletin date and option expiration dates.
    """

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    bulletin_date: date | None = None

    for line in lines[:20]:
        match = BULLETIN_DATE_PATTERN.search(line)

        if match is None:
            continue

        bulletin_date = datetime.strptime(
            (
                f"{match.group('month')} "
                f"{match.group('day')} "
                f"{match.group('year')}"
            ),
            "%b %d %Y",
        ).date()

        break

    if bulletin_date is None:
        raise CMEOptionsError(
            "Unable to parse CME bulletin date."
        )

    expiration_codes: list[str] | None = None
    expiration_dates: list[str] | None = None

    for index, line in enumerate(lines):

        if line.startswith("LEAN HOGS OPT "):
            expiration_dates = line.split()[3:]
        elif line.startswith("LV CATTLE OPT "):
            expiration_dates = line.split()[3:]
        else:
            continue

        if index == 0:
            break

        expiration_codes = lines[index - 2].split()

        break

    if (
        expiration_codes is None
        or expiration_dates is None
    ):
        raise CMEOptionsError(
            "Unable to parse CME option expiration dates."
        )

    if len(expiration_codes) != len(expiration_dates):
        raise CMEOptionsError(
            "CME option expiration codes and dates "
            "have different lengths."
        )

    option_expirations: dict[str, date] = {}

    for expiration_code, month_day in zip(
        expiration_codes,
        expiration_dates,
    ):
        month_text, day_text = month_day.split("/")

        month = int(month_text)
        day = int(day_text)

        contract_year = 2000 + int(
            expiration_code[-2:]
        )

        contract_month_text = (
            expiration_code[:3]
        )

        contract_month = datetime.strptime(
            contract_month_text,
            "%b",
        ).month

        year = contract_year

        if month > contract_month:
            year -= 1

        option_expirations[expiration_code] = date(
            year,
            month,
            day,
        )

    return BulletinMetadata(
        bulletin_date=bulletin_date,
        option_expirations=option_expirations,
    )


def normalize_series_label(
    label: str | None,
) -> str:
    """
    Normalize the option-series label found in the bulletin header.
    """

    if label is None:
        return "STANDARD"

    normalized = label.strip().upper()

    if not normalized or normalized in {
        "LEAN HOGS CALL",
        "LEAN HOGS PUT",
        "LV CATTLE CALL",
        "LV CATTLE PUT",
    }:
        return "STANDARD"

    if normalized == "WLC OPT":
        return "WLC"

    return normalized


def parse_volume_oi_row(
    line: str,
) -> tuple[int, int, int, str] | None:
    """
    Parse volume, open interest and raw strike from one CME option row.
    """

    patterns = (
        ("NEW", NEW_ROW_PATTERN),
        ("ACTIVE", ACTIVE_ROW_PATTERN),
        ("CAB", CAB_ROW_PATTERN),
        ("SIGNED_UNCH", SIGNED_UNCH_ROW_PATTERN),
        ("NO_CHANGE", NO_CHANGE_ROW_PATTERN),
    )

    for format_name, pattern in patterns:
        match = pattern.match(line)

        if match is None:
            continue

        volume_text = match.group("volume")

        volume = (
            0
            if volume_text == "----"
            else int(volume_text)
        )

        open_interest_text = match.group(
            "open_interest"
        )

        open_interest = (
            0
            if open_interest_text == "----"
            else int(open_interest_text)
        )

        strike_text = (
            match.group("strike")
            or match.group("exercise_strike")
        )

        return (
            int(strike_text),
            volume,
            open_interest,
            format_name,
        )

    return None


def parse_option_settlement_row(
    line: str,
) -> float | None:
    """
    Parse option settlement price from one CME option row.

    Cabinet settlements are returned as None because CAB is not
    treated as a numeric settlement price.
    """

    parsed_row = parse_volume_oi_row(
        line
    )

    if parsed_row is None:
        return None

    tokens = line.split()

    if len(tokens) < 5:
        return None

    if tokens[3] != "----":
        return None

    settlement_text = tokens[4]

    if settlement_text == "CAB":
        return None

    try:
        return float(
            settlement_text
        )
    except ValueError:
        return None
    

def _parse_option_text(
    text: str,
    option_type: str,
    strike_scale: float,
) -> list[CMEOptionPoint]:
    """
    Parse option series, expiration, settlement, delta, volume, open interest and strikes.
    """

    if strike_scale <= 0:
        raise ValueError(
            "strike_scale must be greater than zero."
        )

    normalized_type = option_type.strip().upper()

    if normalized_type not in {"CALL", "PUT"}:
        raise ValueError(
            "option_type must be CALL or PUT."
        )

    points: list[CMEOptionPoint] = []

    current_expiration: str | None = None
    current_futures_settlement: float | None = None
    current_series = "STANDARD"

    section_volume = 0
    section_open_interest = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        header_match = SECTION_HEADER_PATTERN.search(line)

        if header_match is not None:
            current_expiration = header_match.group("expiration")
            current_futures_settlement = float(
                header_match.group("settlement")
            )
            current_series = normalize_series_label(
                header_match.group("series_label")
            )

            section_volume = 0
            section_open_interest = 0

            continue

        if current_expiration is None:
            continue

        total_match = TOTAL_PATTERN.search(line)

        if total_match is not None:
            reported_volume = int(
                total_match.group("volume")
            )
            reported_open_interest = int(
                total_match.group("open_interest")
            )

            if section_volume != reported_volume:
                raise CMEOptionsError(
                    "CME option volume validation failed: "
                    f"{current_series} "
                    f"{current_expiration} "
                    f"{normalized_type}: "
                    f"parsed={section_volume:,}, "
                    f"reported={reported_volume:,}."
                )

            if section_open_interest != reported_open_interest:
                raise CMEOptionsError(
                    "CME option open-interest validation failed: "
                    f"{current_series} "
                    f"{current_expiration} "
                    f"{normalized_type}: "
                    f"parsed={section_open_interest:,}, "
                    f"reported={reported_open_interest:,}."
                )

            current_expiration = None
            current_futures_settlement = None
            current_series = "STANDARD"

            section_volume = 0
            section_open_interest = 0

            continue

        parsed_row = parse_volume_oi_row(line)

        if parsed_row is None:
            continue

        (
            strike_raw,
            volume,
            open_interest,
            _format_name,
        ) = parsed_row

        section_volume += volume
        section_open_interest += open_interest

        strike = strike_raw / strike_scale

        option_settlement = (
            parse_option_settlement_row(line)
        )

        tail_match = ROW_TAIL_PATTERN.search(line)

        delta = (
            float(tail_match.group("delta"))
            if tail_match is not None
            else None
        )

        points.append(
            CMEOptionPoint(
                series=current_series,
                expiration_code=current_expiration,
                option_type=normalized_type,
                strike_raw=strike_raw,
                strike=strike,
                futures_settlement=(
                    current_futures_settlement
                ),
                option_settlement=(
                    option_settlement
                ),
                delta=delta,
                volume=volume,
                open_interest=open_interest,
            )
        )

    return points


def _files_for_instrument(
    instrument: InstrumentConfig,
) -> BulletinFiles:
    """
    Resolve CME bulletin filenames from instrument metadata.
    """

    root = instrument.futures_root.strip().upper()

    try:
        return BULLETIN_FILES[root]

    except KeyError as exc:
        raise CMEOptionsError(
            "No CME options bulletin configured "
            f"for futures root {root!r}."
        ) from exc


def collect_options_chain(
    instrument: InstrumentConfig,
) -> CMEOptionsChain:
    """
    Collect CME option strikes together with bulletin metadata.
    """

    files = _files_for_instrument(instrument)

    call_text = _extract_text(
        _download_pdf(files.calls)
    )
    put_text = _extract_text(
        _download_pdf(files.puts)
    )

    metadata = _parse_bulletin_metadata(
        call_text
    )

    settlements = _section_futures_settlements(
        call_text
    )

    calls = _parse_option_text(
        text=call_text,
        option_type="CALL",
        strike_scale=instrument.option_strike_scale,
    )

    puts = _parse_option_text(
        text=put_text,
        option_type="PUT",
        strike_scale=instrument.option_strike_scale,
    )

    calls = _resolve_underlying_settlements(
        points=calls,
        settlements=settlements,
        instrument=instrument,
    )

    puts = _resolve_underlying_settlements(
        points=puts,
        settlements=settlements,
        instrument=instrument,
    )

    points = tuple(
        calls + puts
    )

    if not points:
        raise CMEOptionsError(
            "No CME option strikes parsed."
        )

    return CMEOptionsChain(
        points=points,
        metadata=metadata,
    )


def collect_options(
    instrument: InstrumentConfig,
) -> tuple[CMEOptionPoint, ...]:
    """
    Collect currently published CME option strikes.
    """

    return collect_options_chain(
        instrument
    ).points


def print_options_sample(
    points: tuple[CMEOptionPoint, ...],
    limit: int = 20,
) -> None:
    """
    Print a small sample of parsed option strikes.
    """

    print("=" * 100)
    print("CME OPTIONS PARSER")
    print("=" * 100)

    print(
        f"{'Series':<10}"
        f"{'Expiration':<12}"
        f"{'Type':<6}"
        f"{'Strike':>10}"
        f"{'Raw':>8}"
        f"{'Fut Settle':>12}"
        f"{'Delta':>8}"
        f"{'Volume':>10}"
        f"{'Open Int':>12}"
    )

    print("-" * 100)

    for point in points[:limit]:
        futures_text = (
            f"{point.futures_settlement:.3f}"
            if point.futures_settlement is not None
            else "-"
        )
        delta_text = (
            f"{point.delta:.3f}"
            if point.delta is not None
            else "-"
        )

        print(
            f"{point.series:<10}"
            f"{point.expiration_code:<12}"
            f"{point.option_type:<6}"
            f"{point.strike:>10.3f}"
            f"{point.strike_raw:>8}"
            f"{futures_text:>12}"
            f"{delta_text:>8}"
            f"{point.volume:>10,}"
            f"{point.open_interest:>12,}"
        )

    print()
    print(f"Parsed records: {len(points):,}")




def _underlying_contract_code(
    expiration_code: str,
    instrument: InstrumentConfig,
) -> str:

    option_month = datetime.strptime(
        expiration_code[:3],
        "%b",
    ).month

    option_year = 2000 + int(
        expiration_code[-2:]
    )

    months = sorted(instrument.contract_months)

    if option_month in months:
        futures_month = option_month
        futures_year = option_year
    else:
        later = [
            month
            for month in months
            if month > option_month
        ]

        if later:
            futures_month = later[0]
            futures_year = option_year
        else:
            futures_month = months[0]
            futures_year = option_year + 1

    month_code = datetime(
        futures_year,
        futures_month,
        1,
    ).strftime("%b").upper()

    return f"{month_code}{futures_year % 100:02d}"

def _section_futures_settlements(
    text: str,
) -> dict[str, float]:

    settlements: dict[str, float] = {}

    for raw_line in text.splitlines():
        match = SECTION_HEADER_PATTERN.search(
            raw_line.strip()
        )

        if match is None:
            continue

        settlement = float(
            match.group("settlement")
        )

        if settlement <= 0:
            continue

        settlements[
            match.group("expiration")
        ] = settlement

    return settlements

def _resolve_underlying_settlements(
    points: list[CMEOptionPoint],
    settlements: dict[str, float],
    instrument: InstrumentConfig,
) -> list[CMEOptionPoint]:
    """
    Assign the settlementing futures contract.
    """

    resolved: list[CMEOptionPoint] = []

    for point in points:
        underlying_code = _underlying_contract_code(
            point.expiration_code,
            instrument,
        )

        futures_settlement = settlements.get(
            underlying_code
        )

        resolved.append(
            replace(
                point,
                futures_settlement=futures_settlement,
            )
        )

    return resolved

