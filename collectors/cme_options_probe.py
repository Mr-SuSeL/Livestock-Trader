"""
CME options Daily Bulletin discovery probe.

This module is intentionally diagnostic.

It verifies that the CME Daily Bulletin option reports can be
downloaded and inspected before a production collector is built.

No contract year or expiration is hardcoded here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO

import requests
from pypdf import PdfReader


SOURCE_NAME = "CME"

BASE_URL = (
    "https://www.cmegroup.com/"
    "daily_bulletin/current"
)


class CMEOptionsProbeError(RuntimeError):
    """Base exception for CME options discovery errors."""


@dataclass(frozen=True, slots=True)
class BulletinDefinition:
    """
    CME Daily Bulletin reports associated with one market.
    """

    name: str
    call_file: str
    put_file: str


BULLETINS: dict[str, BulletinDefinition] = {
    "lean_hogs": BulletinDefinition(
        name="Lean Hogs",
        call_file="Section19_Lean_Hogs_Call_Options.pdf",
        put_file="Section20_Lean_Hogs_Put_Options.pdf",
    ),
    "live_cattle": BulletinDefinition(
        name="Live Cattle",
        call_file="Section15_Live_Cattle_Call_Options.pdf",
        put_file="Section16_Live_Cattle_Put_Options.pdf",
    ),
}


OPTION_ROW_PATTERN = re.compile(
    r"""
    ^
    (?P<prefix>.*?)
    \s+
    (?P<strike>\d+)
    $
    """,
    re.VERBOSE,
)

ROW_TAIL_PATTERN = re.compile(
    r"""
    (?P<delta>\.\d{3}|1\.000)
    \s+
    ----
    (?P<strike>\d+)
    $
    """,
    re.VERBOSE,
)

VOLUME_OI_PATTERN = re.compile(
    r"""
    (?P<settlement>
        CAB
        |
        \d*\.\d+
    )
    \s+
    (?P<price_change_sign>[+-]|----)
    \s*
    (?P<volume>\d+|----)
    \s+
    (?P<open_interest>\d+)
    \s+
    (?P<oi_change>[+-]?\d+|UNCH)
    \s+
    (?P<cleared>\d+|UNCH)
    \s+
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
    ----
    (?P<strike>\d+)
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
    (?P<change>[+-]?\d+|UNCH|----|-----)
    \s+
    (?P<trades>\d+|UNCH)
    .*?
    ----
    (?P<strike>\d+)
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
    ----
    (?P<strike>\d+)
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
    ----
    (?P<strike>\d+)
    $
    """,
    re.VERBOSE,
)


def inspect_unparsed_rows(
    market_key: str,
    option_type: str,
    expiration: str,
) -> None:
    """
    Print option rows that the current volume/OI parser
    does not recognize.

    Diagnostic only.
    """

    normalized_market = (
        market_key
        .strip()
        .lower()
    )

    normalized_type = (
        option_type
        .strip()
        .upper()
    )

    normalized_expiration = (
        expiration
        .strip()
        .upper()
    )

    definition = BULLETINS[
        normalized_market
    ]

    if normalized_type == "CALL":
        filename = definition.call_file
    elif normalized_type == "PUT":
        filename = definition.put_file
    else:
        raise ValueError(
            "option_type must be CALL or PUT."
        )

    text = extract_text(
        download_pdf(
            bulletin_url(filename)
        )
    )

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    header_pattern = re.compile(
        r"""
        FUTURES\s+SETT\.
        .*?
        (?P<expiration>
            [A-Z]{3}\d{2}
        )
        $
        """,
        re.VERBOSE,
    )

    active_expiration = None

    candidates = 0
    parsed = 0
    missed = 0

    print("=" * 90)
    print(
        f"{definition.name} "
        f"{normalized_type} "
        f"{normalized_expiration}"
    )
    print("=" * 90)

    for line in lines:

        header_match = (
            header_pattern.search(
                line
            )
        )

        if header_match is not None:
            active_expiration = (
                header_match.group(
                    "expiration"
                )
            )
            continue

        if active_expiration != normalized_expiration:
            continue

        if line.startswith("TOTAL"):
            print()
            print(
                f"REPORTED: {line}"
            )
            break

        strike_match = re.search(
            r"----(?P<strike>\d+)\s*$",
            line,
        )

        if strike_match is None:
            continue

        candidates += 1

        parsed_row = parse_volume_oi_row(
            line
        )

        if parsed_row is not None:
            parsed += 1
            continue

        missed += 1

        strike_raw = int(
            strike_match.group(
                "strike"
            )
        )

        print(
            f"MISS {strike_raw:>5} | "
            f"{line}"
        )

    print()
    print(
        f"Candidate rows: {candidates}"
    )
    print(
        f"Parsed rows:    {parsed}"
    )
    print(
        f"Missed rows:    {missed}"
    )

def bulletin_url(
    filename: str,
) -> str:
    """
    Return the current CME Daily Bulletin URL.
    """

    return f"{BASE_URL}/{filename}"


def download_pdf(
    url: str,
    timeout: float = 30.0,
) -> bytes:
    """
    Download one CME bulletin PDF.
    """

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
        raise CMEOptionsProbeError(
            f"CME request failed: {exc}"
        ) from exc

    content = response.content

    if not content.startswith(b"%PDF"):
        raise CMEOptionsProbeError(
            "CME response is not a PDF."
        )

    return content


def extract_text(
    pdf_bytes: bytes,
) -> str:
    """
    Extract text from a CME bulletin PDF.
    """

    try:
        reader = PdfReader(
            BytesIO(pdf_bytes)
        )

        pages = []

        for page in reader.pages:
            text = page.extract_text()

            if text:
                pages.append(text)

    except Exception as exc:
        raise CMEOptionsProbeError(
            f"Unable to parse CME PDF: {exc}"
        ) from exc

    result = "\n".join(pages).strip()

    if not result:
        raise CMEOptionsProbeError(
            "No text extracted from CME PDF."
        )

    return result


def print_text_sample(
    title: str,
    text: str,
    lines: int = 120,
) -> None:
    """
    Print the first useful lines from extracted bulletin text.
    """

    print()
    print("-" * 70)
    print(title)
    print("-" * 70)

    useful_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    for line in useful_lines[:lines]:
        print(line)


def probe_report(
    title: str,
    filename: str,
) -> bool:
    """
    Download and inspect one bulletin report.
    """

    url = bulletin_url(filename)

    print()
    print(f"Report: {title}")
    print(f"URL:    {url}")

    try:
        pdf_bytes = download_pdf(url)
        text = extract_text(pdf_bytes)

    except CMEOptionsProbeError as exc:
        print("Status: FAILED")
        print(f"Reason: {exc}")
        return False

    print("Status: OK")
    print(f"PDF bytes: {len(pdf_bytes):,}")
    print(f"Text chars: {len(text):,}")

    print_text_sample(
        title=title,
        text=text,
    )

    return True


def probe_market(
    market_key: str,
) -> bool:
    """
    Probe call and put Daily Bulletin reports for one market.
    """

    normalized = market_key.strip().lower()

    try:
        definition = BULLETINS[normalized]

    except KeyError as exc:
        available = ", ".join(sorted(BULLETINS))

        raise CMEOptionsProbeError(
            f"Unknown market: {market_key!r}. "
            f"Available: {available}"
        ) from exc

    print("=" * 70)
    print("CME OPTIONS DAILY BULLETIN PROBE")
    print("=" * 70)

    print(f"Market: {definition.name}")

    call_ok = probe_report(
        title=f"{definition.name} CALLS",
        filename=definition.call_file,
    )

    put_ok = probe_report(
        title=f"{definition.name} PUTS",
        filename=definition.put_file,
    )

    print()
    print("=" * 70)

    if call_ok and put_ok:
        print("OVERALL STATUS: OK")
        return True

    print("OVERALL STATUS: FAILED")
    return False


def inspect_matching_lines(
    market_key: str,
    option_type: str,
    pattern: str,
) -> None:
    """
    Print extracted PDF lines containing a literal pattern.
    """

    normalized_market = market_key.strip().lower()
    normalized_type = option_type.strip().upper()

    definition = BULLETINS[normalized_market]

    if normalized_type == "CALL":
        filename = definition.call_file
    elif normalized_type == "PUT":
        filename = definition.put_file
    else:
        raise ValueError("option_type must be CALL or PUT.")

    text = extract_text(download_pdf(bulletin_url(filename)))

    print("=" * 70)
    print(f"{definition.name} {normalized_type}")
    print("=" * 70)

    matches = 0

    for line_number, line in enumerate(
        text.splitlines(),
        start=1,
    ):
        if pattern in line:
            print(f"{line_number:>5}: {line}")
            matches += 1

    print()
    print(f"Matches: {matches}")


def parse_volume_oi_row(
    line: str,
) -> tuple[int, int, int, str] | None:
    """
    Parse volume, open interest and strike from one CME option row.

    Return:
        strike_raw
        volume
        open_interest
        matched_format
    """

    patterns = (
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

        if volume_text == "----":
            volume = 0
        else:
            volume = int(volume_text)

        return (
            int(match.group("strike")),
            volume,
            int(match.group("open_interest")),
            format_name,
        )

    return None


def inspect_parsed_rows(
    market_key: str,
    option_type: str,
    expiration: str,
    limit: int = 100,
) -> None:
    """
    Inspect candidate parsing of CME option volume and open interest.

    Diagnostic only.
    """

    normalized_market = market_key.strip().lower()
    normalized_type = option_type.strip().upper()
    normalized_expiration = expiration.strip().upper()

    definition = BULLETINS[normalized_market]

    if normalized_type == "CALL":
        filename = definition.call_file
    elif normalized_type == "PUT":
        filename = definition.put_file
    else:
        raise ValueError("option_type must be CALL or PUT.")

    text = extract_text(download_pdf(bulletin_url(filename)))

    active = False
    records = []
    reported_total = None

    section_marker = f"){normalized_expiration}"

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if (
            "FUTURES SETT." in line
            and section_marker in line
        ):
            active = True
            continue

        if not active:
            continue

        if line.startswith("TOTAL"):
            reported_total = line
            break

        if "FUTURES SETT." in line:
            break

        parsed_row = parse_volume_oi_row(line)

        if parsed_row is None:
            continue

        (
            strike_raw,
            volume,
            open_interest,
            format_name,
        ) = parsed_row

        records.append(
            (
                strike_raw,
                volume,
                open_interest,
                format_name,
                line,
            )
        )

    print("=" * 70)
    print(
        f"{definition.name} "
        f"{normalized_type} "
        f"{normalized_expiration}"
    )
    print("=" * 70)

    for (
        strike_raw,
        volume,
        open_interest,
        format_name,
        original,
    ) in records[:limit]:

        print()
        print(f"STRIKE {strike_raw} [{format_name}]")
        print(f"  Volume: {volume:,} | OI: {open_interest:,}")
        print(f"  RAW: {original}")

    print()
    print(f"Rows found: {len(records)}")

    if reported_total is not None:
        print(f"Reported: {reported_total}")


def inspect_section_matches(
    market_key: str,
    option_type: str,
    expiration: str,
) -> None:
    """
    Show every option row in a section and whether the
    candidate volume/OI regex recognizes it.
    """

    normalized_market = market_key.strip().lower()
    normalized_type = option_type.strip().upper()
    normalized_expiration = expiration.strip().upper()

    definition = BULLETINS[normalized_market]

    if normalized_type == "CALL":
        filename = definition.call_file
    elif normalized_type == "PUT":
        filename = definition.put_file
    else:
        raise ValueError("option_type must be CALL or PUT.")

    text = extract_text(download_pdf(bulletin_url(filename)))

    active = False
    section_marker = f"){normalized_expiration}"

    matched = 0
    missed = 0

    print("=" * 70)
    print(
        f"{definition.name} "
        f"{normalized_type} "
        f"{normalized_expiration}"
    )
    print("=" * 70)

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if (
            "FUTURES SETT." in line
            and section_marker in line
        ):
            active = True
            continue

        if not active:
            continue

        if line.startswith("TOTAL"):
            print()
            print(f"REPORTED: {line}")
            break

        if "FUTURES SETT." in line:
            break

        if not re.search(r"----\s*\d+\s*$", line):
            continue

        parsed = parse_volume_oi_row(line)

        if parsed is None:
            status = "MISS "
            missed += 1
        else:
            status = "MATCH"
            matched += 1

        print(f"{status} | {line}")

    print()
    print(f"Matched: {matched}")
    print(f"Missed:  {missed}")


def inspect_context(
    market_key: str,
    option_type: str,
    pattern: str,
    before: int = 5,
    after: int = 5,
) -> None:
    """
    Print matching PDF lines together with surrounding context.
    """

    normalized_market = market_key.strip().lower()
    normalized_type = option_type.strip().upper()

    definition = BULLETINS[normalized_market]

    if normalized_type == "CALL":
        filename = definition.call_file
    elif normalized_type == "PUT":
        filename = definition.put_file
    else:
        raise ValueError("option_type must be CALL or PUT.")

    text = extract_text(download_pdf(bulletin_url(filename)))

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    matches = [
        index
        for index, line in enumerate(lines)
        if pattern in line
    ]

    print("=" * 90)
    print(f"{definition.name} {normalized_type}")
    print("=" * 90)

    for match_number, index in enumerate(
        matches,
        start=1,
    ):
        print()
        print(f"--- MATCH {match_number} @ line {index + 1} ---")

        start = max(0, index - before)
        end = min(len(lines), index + after + 1)

        for context_index in range(start, end):
            marker = ">>>" if context_index == index else "   "
            print(f"{marker} {context_index + 1:5}: {lines[context_index]}")


def inspect_volume_oi(
    market_key: str,
    option_type: str,
    expiration: str,
    limit: int = 50,
) -> None:
    """
    Diagnostic parser for CME volume/open-interest fields.
    """

    normalized_market = market_key.strip().lower()
    normalized_type = option_type.strip().upper()
    normalized_expiration = expiration.strip().upper()

    definition = BULLETINS[normalized_market]

    if normalized_type == "CALL":
        filename = definition.call_file
    elif normalized_type == "PUT":
        filename = definition.put_file
    else:
        raise ValueError("option_type must be CALL or PUT.")

    text = extract_text(download_pdf(bulletin_url(filename)))

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    header_pattern = re.compile(
        r"""
        FUTURES\s+SETT\.
        .*?
        (?P<expiration>
            [A-Z]{3}\d{2}
        )
        $
        """,
        re.VERBOSE,
    )

    active_expiration = None
    rows = []

    reported_volume = None
    reported_oi = None

    for line in lines:
        header_match = header_pattern.search(line)

        if header_match is not None:
            active_expiration = header_match.group("expiration")
            continue

        if active_expiration != normalized_expiration:
            continue

        if line.startswith("TOTAL"):
            total_match = re.search(
                r"""
                ^TOTAL
                \s+
                (?P<volume>\d+)
                \s+
                (?P<open_interest>\d+)
                """,
                line,
                re.VERBOSE,
            )

            if total_match is not None:
                reported_volume = int(total_match.group("volume"))
                reported_oi = int(total_match.group("open_interest"))

            break

        parsed_row = parse_volume_oi_row(
            line
        )

        if parsed_row is None:
            continue

        (
            strike_raw,
            volume,
            open_interest,
            format_name,
        ) = parsed_row

        rows.append(
            (
                strike_raw,
                strike_raw / 10.0,
                volume,
                open_interest,
            )
        )

    print("=" * 90)
    print(f"{definition.name} {normalized_type} {normalized_expiration}")
    print("=" * 90)

    print(f"{'Strike':>10}{'Volume':>12}{'Open Int':>14}")
    print("-" * 90)

    for _, strike, volume, open_interest in rows[:limit]:
        print(f"{strike:>10.1f}{volume:>12,}{open_interest:>14,}")

    parsed_volume = sum(row[2] for row in rows)
    parsed_oi = sum(row[3] for row in rows)

    print()
    print(f"Rows matched:       {len(rows):,}")
    print()
    print(f"Parsed volume:      {parsed_volume:,}")
    print(
        f"Reported volume:    {reported_volume:,}"
        if reported_volume is not None
        else "Reported volume:    UNKNOWN"
    )

    print()
    print(f"Parsed OI:          {parsed_oi:,}")
    print(
        f"Reported OI:        {reported_oi:,}"
        if reported_oi is not None
        else "Reported OI:        UNKNOWN"
    )

    volume_ok = (
        reported_volume is not None
        and parsed_volume == reported_volume
    )
    oi_ok = (
        reported_oi is not None
        and parsed_oi == reported_oi
    )

    print()
    print(f"Volume validation:  {'PASS' if volume_ok else 'FAIL'}")
    print(f"OI validation:      {'PASS' if oi_ok else 'FAIL'}")


def inspect_row_tails(
    market_key: str,
    option_type: str,
    expiration: str,
    limit: int = 20,
) -> None:
    """
    Diagnostic parser for CME option row tails.

    Extract only:
        - raw strike
        - delta

    No other columns are interpreted yet.
    """

    normalized_market = market_key.strip().lower()
    normalized_type = option_type.strip().upper()
    normalized_expiration = expiration.strip().upper()

    definition = BULLETINS[normalized_market]

    if normalized_type == "CALL":
        filename = definition.call_file
    elif normalized_type == "PUT":
        filename = definition.put_file
    else:
        raise ValueError("option_type must be CALL or PUT.")

    text = extract_text(download_pdf(bulletin_url(filename)))

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    header_pattern = re.compile(
        r"""
        FUTURES\s+SETT\.
        .*?
        (?P<expiration>
            [A-Z]{3}\d{2}
        )
        $
        """,
        re.VERBOSE,
    )

    active_expiration = None
    rows = []

    for line in lines:
        header_match = header_pattern.search(line)

        if header_match is not None:
            active_expiration = header_match.group("expiration")
            continue

        if line.startswith("TOTAL"):
            if active_expiration == normalized_expiration:
                break
            continue

        if active_expiration != normalized_expiration:
            continue

        match = ROW_TAIL_PATTERN.search(line)

        if match is None:
            continue

        strike_raw = int(match.group("strike"))
        delta = float(match.group("delta"))

        rows.append(
            (
                strike_raw,
                strike_raw / 10.0,
                delta,
                line,
            )
        )

    print("=" * 90)
    print(f"{definition.name} {normalized_type} {normalized_expiration}")
    print("=" * 90)

    print(f"{'Raw':>8}{'Strike':>10}{'Delta':>10}")
    print("-" * 90)

    for strike_raw, strike, delta, _ in rows[:limit]:
        print(f"{strike_raw:>8}{strike:>10.1f}{delta:>10.3f}")

    print()
    print(f"Rows matched: {len(rows):,}")

    if rows:
        print(f"Strike range: {rows[0][1]:.1f} -> {rows[-1][1]:.1f}")

@dataclass(frozen=True, slots=True)
class ValidationResult:
    series: str
    expiration: str
    option_type: str

    rows: int

    parsed_volume: int
    reported_volume: int

    parsed_oi: int
    reported_oi: int

    @property
    def volume_ok(self) -> bool:
        return (
            self.parsed_volume
            == self.reported_volume
        )

    @property
    def oi_ok(self) -> bool:
        return (
            self.parsed_oi
            == self.reported_oi
        )

    @property
    def ok(self) -> bool:
        return (
            self.volume_ok
            and self.oi_ok
        )

def normalize_series_label(
    label: str | None,
) -> str:
    """
    Normalize the option-series label found in the bulletin.
    """

    if label is None:
        return "STANDARD"

    normalized = (
        label
        .strip()
        .upper()
    )

    if not normalized:
        return "STANDARD"

    if normalized in {
        "LEAN HOGS CALL",
        "LEAN HOGS PUT",
        "LV CATTLE CALL",
        "LV CATTLE PUT",
    }:
        return "STANDARD"

    if normalized == "WLC OPT":
        return "WLC"

    return normalized

VALIDATION_HEADER_PATTERN = re.compile(
    r"""
    ^
    (?P<series_label>.*?)?
    \(?
    FUTURES\s+SETT\.
    .*?
    \)?
    (?P<expiration>[A-Z]{3}\d{2})
    $
    """,
    re.VERBOSE,
)

VALIDATION_TOTAL_PATTERN = re.compile(
    r"""
    ^TOTAL
    \s+
    (?P<volume>\d+)
    \s+
    (?P<open_interest>\d+)
    """,
    re.VERBOSE,
)


def validate_option_text(
    text: str,
    option_type: str,
) -> list[ValidationResult]:
    """
    Validate all expiration sections in one CME option bulletin.
    """

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

    results: list[ValidationResult] = []

    current_expiration: str | None = None
    current_series = "STANDARD"

    parsed_volume = 0
    parsed_oi = 0
    rows = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        header_match = (
            VALIDATION_HEADER_PATTERN.search(
                line
            )
        )

        if header_match is not None:

            current_expiration = (
                header_match.group(
                    "expiration"
                )
            )

            current_series = normalize_series_label(
                header_match.group(
                    "series_label"
                )
            )

            parsed_volume = 0
            parsed_oi = 0
            rows = 0

            continue

        if current_expiration is None:
            continue

        total_match = (
            VALIDATION_TOTAL_PATTERN.search(
                line
            )
        )

        if total_match is not None:

            results.append(
                ValidationResult(
                    series=current_series,
                    expiration=current_expiration,
                    option_type=normalized_type,
                    rows=rows,
                    parsed_volume=parsed_volume,
                    reported_volume=int(
                        total_match.group(
                            "volume"
                        )
                    ),
                    parsed_oi=parsed_oi,
                    reported_oi=int(
                        total_match.group(
                            "open_interest"
                        )
                    ),
                )
            )

            current_expiration = None

            parsed_volume = 0
            parsed_oi = 0
            rows = 0

            continue

        parsed_row = parse_volume_oi_row(
            line
        )

        if parsed_row is None:
            continue

        (
            _strike_raw,
            volume,
            open_interest,
            _format_name,
        ) = parsed_row

        rows += 1

        parsed_volume += volume
        parsed_oi += open_interest

    return results


def validate_market(
    market_key: str,
) -> bool:
    """
    Validate every expiration found in both CME option bulletins.
    """

    normalized_market = (
        market_key
        .strip()
        .lower()
    )

    try:
        definition = BULLETINS[
            normalized_market
        ]
    except KeyError as exc:
        available = ", ".join(
            sorted(BULLETINS)
        )

        raise CMEOptionsProbeError(
            f"Unknown market: {market_key!r}. "
            f"Available: {available}"
        ) from exc

    reports = (
        (
            "CALL",
            definition.call_file,
        ),
        (
            "PUT",
            definition.put_file,
        ),
    )

    results: list[ValidationResult] = []

    for option_type, filename in reports:

        text = extract_text(
            download_pdf(
                bulletin_url(
                    filename
                )
            )
        )

        results.extend(
            validate_option_text(
                text=text,
                option_type=option_type,
            )
        )

    print("=" * 110)
    print(
        f"CME OPTIONS VALIDATION - "
        f"{definition.name}"
    )
    print("=" * 110)

    print(
        f"{'Series':<18}"
        f"{'Expiration':<12}"
        f"{'Type':<8}"
        f"{'Rows':>8}"
        f"{'Volume':>22}"
        f"{'Open Interest':>26}"
        f"{'Status':>12}"
    )


    print("-" * 110)

    for result in results:

        volume_text = (
            f"{result.parsed_volume:,}"
            f"/"
            f"{result.reported_volume:,}"
        )

        oi_text = (
            f"{result.parsed_oi:,}"
            f"/"
            f"{result.reported_oi:,}"
        )

        status = (
            "PASS"
            if result.ok
            else "FAIL"
        )

        print(
            f"{result.series:<18}"
            f"{result.expiration:<12}"
            f"{result.option_type:<8}"
            f"{result.rows:>8,}"
            f"{volume_text:>22}"
            f"{oi_text:>26}"
            f"{status:>12}"
        )


    print("-" * 110)

    if not results:
        print(
            "OVERALL VALIDATION: FAIL"
        )
        print(
            "No expiration sections found."
        )
        return False

    failed = [
        result
        for result in results
        if not result.ok
    ]

    print()

    if failed:
        print(
            "OVERALL VALIDATION: FAIL"
        )

        print(
            f"Failed sections: "
            f"{len(failed)}"
        )

        return False

    print(
        "OVERALL VALIDATION: PASS"
    )

    print(
        f"Validated sections: "
        f"{len(results)}"
    )

    return True

def main() -> None:
    """
    Run Lean Hogs discovery probe.
    """

    probe_market("lean_hogs")


if __name__ == "__main__":
    main()