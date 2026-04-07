#!/usr/bin/env python3
"""Fetch Horizons vector ephemeris and save positions to CSV.

Default behavior:
- Reads the first URL from README.md in the same directory
- Downloads ephemeris text from JPL Horizons API
- Parses epochs and position components (X, Y, Z)
- Writes CSV with UTC time, JD, and position components
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen


SOE_MARKER = "$$SOE"
EOE_MARKER = "$$EOE"
URL_RE = re.compile(r"https?://\S+")
EPOCH_RE = re.compile(r"^\s*([0-9]+\.[0-9]+)\s*=\s*(.+?)\s*$")
POS_RE = re.compile(
    r"X\s*=\s*([+-]?\d+(?:\.\d+)?(?:E[+-]?\d+)?)\s+"
    r"Y\s*=\s*([+-]?\d+(?:\.\d+)?(?:E[+-]?\d+)?)\s+"
    r"Z\s*=\s*([+-]?\d+(?:\.\d+)?(?:E[+-]?\d+)?)"
)


def read_endpoint_from_readme(readme_path: Path) -> str:
    text = readme_path.read_text(encoding="utf-8")
    match = URL_RE.search(text)
    if not match:
        raise ValueError(f"No URL found in {readme_path}")
    return match.group(0)


def fetch_text(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported URL scheme in endpoint: {url}")

    try:
        with urlopen(url) as response:
            return response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raise RuntimeError(f"HTTP error while fetching ephemeris: {exc}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error while fetching ephemeris: {exc}") from exc


def parse_vectors(api_text: str) -> list[dict[str, float | str]]:
    lines = api_text.splitlines()
    try:
        start = lines.index(SOE_MARKER) + 1
        end = lines.index(EOE_MARKER)
    except ValueError as exc:
        raise ValueError("Could not find $$SOE/$$EOE block in API response") from exc

    rows: list[dict[str, float | str]] = []
    current_jd: float | None = None
    current_utc: str | None = None

    for line in lines[start:end]:
        epoch_match = EPOCH_RE.match(line)
        if epoch_match:
            current_jd = float(epoch_match.group(1))
            current_utc = epoch_match.group(2).replace("A.D. ", "").replace(" UTC", "")
            continue

        pos_match = POS_RE.search(line)
        if pos_match and current_jd is not None and current_utc is not None:
            x = float(pos_match.group(1))
            y = float(pos_match.group(2))
            z = float(pos_match.group(3))
            rows.append(
                {
                    "utc": current_utc,
                    "jdut": current_jd,
                    "x_km": x,
                    "y_km": y,
                    "z_km": z,
                }
            )

    if not rows:
        raise ValueError("No position records parsed from ephemeris response")
    return rows


def write_csv(rows: list[dict[str, float | str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["utc", "jdut", "x_km", "y_km", "z_km"]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Fetch Horizons vectors and save positions to CSV."
    )
    parser.add_argument(
        "--endpoint",
        default=None,
        help="Horizons API URL. If omitted, first URL in README.md is used.",
    )
    parser.add_argument(
        "--readme",
        default=str(here / "README.md"),
        help="Path to README containing endpoint URL (used when --endpoint omitted).",
    )
    parser.add_argument(
        "--out",
        default=str(here / "ephemeris_positions.csv"),
        help="Output CSV file path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    readme_path = Path(args.readme)
    output_path = Path(args.out)

    try:
        endpoint = args.endpoint or read_endpoint_from_readme(readme_path)
        print(f"Fetching ephemeris from: {endpoint}")
        api_text = fetch_text(endpoint)
        rows = parse_vectors(api_text)
        write_csv(rows, output_path)
        print(f"Wrote {len(rows)} rows to: {output_path}")
        return 0
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
