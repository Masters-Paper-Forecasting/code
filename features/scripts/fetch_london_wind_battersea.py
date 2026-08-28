#!/usr/bin/env python3
"""
Fetch hourly London wind speed and direction from Battersea Heliport (MIDAS Open).

Source: Met Office MIDAS Open UK mean wind observations (CEDA).
https://catalogue.ceda.ac.uk/uuid/c7393fdc2c974071a2efd7f8601b1bab/

Battersea Heliport (src_id 62084) is the closest MIDAS wind station to
London Marylebone Road (~6 km). Exports native hourly mean wind speed (knots)
and direction (degrees true). Resampling and daily alignment are done in the
notebook.

Usage:
  export CEDA_USERNAME='your_ceda_username'
  export CEDA_PASSWORD='your_ceda_password'
  python features/scripts/fetch_london_wind_battersea.py

  python features/scripts/fetch_london_wind_battersea.py --start-year 2022 --end-date 2025-12-31

  # Optional: filter Battersea rows from an existing hourly CSV:
  python features/scripts/fetch_london_wind_battersea.py --from-local path/to/hourly_wind.csv

Register for CEDA (free): https://services.ceda.ac.uk/cedasite/register
"""

from __future__ import annotations

import argparse
import base64
import csv
import http.cookiejar
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
from typing import Callable

import pandas as pd

CEDA_ARCHIVE_BROWSER = "https://data.ceda.ac.uk"
CEDA_SIGNIN_URL = "https://auth.ceda.ac.uk/account/signin/"
CEDA_TOKEN_URL = "https://services.ceda.ac.uk/api/token/create/"
MIDAS_WIND_ROOT = "/badc/ukmo-midas-open/data/uk-mean-wind-obs"
MIDAS_QC_VERSION = "qc-version-1"
CEDA_END_DATE = date(2025, 12, 31)

STATION_NAME = "BATTERSEA HELIPORT"
SRC_ID = "62084"
HISTORIC_COUNTY = "greater-london"
STATION_FILE_NAME = "battersea-heliport"
DEFAULT_OUTPUT = REPO_ROOT / "data/london_wind_hourly.csv"

WIND_COLUMNS = ["ob_end_time", "src_id", "mean_wind_speed", "mean_wind_dir"]


def _is_badc_csv(payload: bytes) -> bool:
    preview = payload[:200].decode("utf-8", errors="replace")
    return preview.startswith("Conventions,G,BADC-CSV")


def _validate_badc_csv_payload(payload: bytes, url: str) -> None:
    if _is_badc_csv(payload):
        return
    preview = payload[:200].decode("utf-8", errors="replace")
    if preview.lstrip().startswith("<!DOCTYPE") or preview.lstrip().startswith("<html"):
        raise RuntimeError(
            "CEDA returned an HTML page instead of a BADC-CSV file. "
            "Check your CEDA credentials or access token."
        )
    raise RuntimeError(f"Download from {url} did not return a BADC-CSV file.")


def _create_ceda_session_opener(username: str, password: str) -> urllib.request.OpenerDirector:
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

    signin_html = opener.open(CEDA_SIGNIN_URL, timeout=60).read().decode("utf-8")
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', signin_html)
    if not match:
        raise RuntimeError("Could not read CEDA login form.")

    payload = urllib.parse.urlencode(
        {
            "csrfmiddlewaretoken": match.group(1),
            "username": username,
            "password": password,
        }
    ).encode("utf-8")
    login_request = urllib.request.Request(
        CEDA_SIGNIN_URL,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": CEDA_SIGNIN_URL,
        },
    )
    opener.open(login_request, timeout=60)
    return opener


def _try_create_ceda_token(username: str, password: str) -> str | None:
    basic = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    request = urllib.request.Request(
        CEDA_TOKEN_URL,
        data=b"",
        method="POST",
        headers={
            "Authorization": f"Basic {basic}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError:
        return None
    return payload.get("access_token")


def _download_with_retries(fetch: Callable[[], bytes], url: str, retries: int = 5) -> bytes:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            payload = fetch()
            _validate_badc_csv_payload(payload, url)
            return payload
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt == retries - 1:
                raise
            time.sleep(min(2 ** attempt, 30))
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == retries - 1:
                raise
            time.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f"Failed to download {url}") from last_error


def _build_ceda_downloader(
    username: str | None,
    password: str | None,
    access_token: str | None,
) -> Callable[[str], bytes]:
    if access_token:
        def download_with_token(url: str) -> bytes:
            def fetch() -> bytes:
                request = urllib.request.Request(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                with urllib.request.urlopen(request, timeout=300) as response:
                    return response.read()

            return _download_with_retries(fetch, url)

        return download_with_token

    if not username or not password:
        raise RuntimeError(
            "CEDA credentials required. Set either:\n"
            "  CEDA_ACCESS_TOKEN\n"
            "  CEDA_USERNAME and CEDA_PASSWORD\n"
            "Register free at https://services.ceda.ac.uk/cedasite/register"
        )

    token = _try_create_ceda_token(username, password)
    if token:
        def download_with_token(url: str) -> bytes:
            def fetch() -> bytes:
                request = urllib.request.Request(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                )
                with urllib.request.urlopen(request, timeout=300) as response:
                    return response.read()

            return _download_with_retries(fetch, url)

        return download_with_token

    opener = _create_ceda_session_opener(username, password)

    def download_with_session(url: str) -> bytes:
        def fetch() -> bytes:
            with opener.open(url, timeout=300) as response:
                return response.read()

        return _download_with_retries(fetch, url)

    return download_with_session


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def _latest_dataset_version() -> str:
    listing = _fetch_json(f"{CEDA_ARCHIVE_BROWSER}{MIDAS_WIND_ROOT}/?json")
    versions = sorted(
        item["name"]
        for item in listing.get("items", [])
        if item.get("type") == "dir" and item["name"].startswith("dataset-version-")
    )
    if not versions:
        raise RuntimeError(f"No MIDAS wind dataset versions found under {MIDAS_WIND_ROOT}")
    return versions[-1]


def _parse_badc_csv(text: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    data_idx = next(i for i, line in enumerate(lines) if line.strip().lower() == "data")
    end_idx = next(i for i, line in enumerate(lines) if line.strip().lower() == "end data")
    header = lines[data_idx + 1].split(",")
    rows: list[dict[str, str]] = []
    for line in lines[data_idx + 2 : end_idx]:
        if not line.strip():
            continue
        values = next(csv.reader([line]))
        rows.append(dict(zip(header, values)))
    return rows


def _year_from_filename(filename: str) -> int | None:
    match = re.search(r"_(\d{4})\.csv$", filename)
    return int(match.group(1)) if match else None


def _station_folder_name(src_id: str, station_file_name: str) -> str:
    return f"{int(src_id):05d}_{station_file_name}"


def _parse_wind_file(payload: bytes, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    rows = _parse_badc_csv(payload.decode("utf-8"))
    if not rows:
        return pd.DataFrame(columns=WIND_COLUMNS)

    frame = pd.DataFrame(rows)
    keep = [col for col in WIND_COLUMNS if col in frame.columns]
    frame = frame[keep].copy()
    frame["ob_end_time"] = pd.to_datetime(frame["ob_end_time"], errors="coerce")
    frame = frame.dropna(subset=["ob_end_time"])
    frame = frame[(frame["ob_end_time"] >= start) & (frame["ob_end_time"] <= end)]
    frame["mean_wind_speed"] = pd.to_numeric(frame["mean_wind_speed"], errors="coerce")
    frame["mean_wind_dir"] = pd.to_numeric(frame["mean_wind_dir"], errors="coerce")
    frame["src_id"] = frame["src_id"].astype(str).str.lstrip("0").replace("", "0")
    return frame


def _date_bounds(start_year: int, end_date: date) -> tuple[pd.Timestamp, pd.Timestamp, date]:
    clipped_end = min(end_date, CEDA_END_DATE)
    start = pd.Timestamp(date(start_year, 1, 1))
    end_ts = pd.Timestamp(datetime.combine(clipped_end, datetime.max.time()))
    if start.date() > clipped_end:
        raise RuntimeError(
            f"No MIDAS wind data to fetch for {start.date()} to {clipped_end}. "
            f"MIDAS Open UK mean wind currently runs through {CEDA_END_DATE}."
        )
    return start, end_ts, clipped_end


def _collect_battersea_download_urls(
    dataset_version: str,
    start_year: int,
    end_year: int,
) -> list[str]:
    county_listing = _fetch_json(f"{CEDA_ARCHIVE_BROWSER}{MIDAS_WIND_ROOT}/{dataset_version}/?json")
    county_path = next(
        item["path"]
        for item in county_listing.get("items", [])
        if item.get("name") == HISTORIC_COUNTY
    )
    folder_name = _station_folder_name(SRC_ID, STATION_FILE_NAME)
    county_items = _fetch_json(f"{CEDA_ARCHIVE_BROWSER}{county_path}/?json")["items"]
    station_path = next(
        item["path"]
        for item in county_items
        if item.get("type") == "dir" and item.get("name") == folder_name
    )
    qc_items = _fetch_json(
        f"{CEDA_ARCHIVE_BROWSER}{station_path}/{MIDAS_QC_VERSION}/?json"
    )["items"]
    year_files = {
        _year_from_filename(item["name"]): item["download"]
        for item in qc_items
        if item.get("type") == "file" and item["name"].endswith(".csv")
    }
    return [
        year_files[year]
        for year in range(start_year, end_year + 1)
        if year in year_files
    ]


def _fetch_battersea_hourly(
    start_year: int,
    end_date: date,
    username: str | None = None,
    password: str | None = None,
    access_token: str | None = None,
    dataset_version: str | None = None,
) -> tuple[pd.DataFrame, str]:
    start, end_ts, clipped_end = _date_bounds(start_year, end_date)
    dataset_version = dataset_version or _latest_dataset_version()
    source_label = f"ceda_midas_open_{dataset_version.replace('dataset-version-', '')}"
    print(f"Using MIDAS Open dataset {dataset_version}")
    print(f"Station: {STATION_NAME} (src_id {SRC_ID})")

    download = _build_ceda_downloader(username, password, access_token)
    urls = _collect_battersea_download_urls(dataset_version, start_year, clipped_end.year)
    if not urls:
        raise RuntimeError("No Battersea MIDAS wind files found for the requested period.")

    frames: list[pd.DataFrame] = []
    for url in urls:
        frame = _parse_wind_file(download(url), start, end_ts)
        if not frame.empty:
            frames.append(frame)

    if not frames:
        raise RuntimeError("Downloads succeeded but no hourly rows matched the date filter.")

    hourly = pd.concat(frames, ignore_index=True).sort_values("ob_end_time").reset_index(drop=True)
    return hourly, source_label


def fetch_london_wind_timeseries(
    output_path: Path = DEFAULT_OUTPUT,
    start_year: int = 2016,
    end_date: date | None = None,
    from_local: Path | None = None,
    username: str | None = None,
    password: str | None = None,
    access_token: str | None = None,
    dataset_version: str | None = None,
) -> pd.DataFrame:
    """Fetch hourly Battersea wind observations from MIDAS Open."""
    end = end_date or date.today()
    username = username or os.environ.get("CEDA_USERNAME")
    password = password or os.environ.get("CEDA_PASSWORD")
    access_token = access_token or os.environ.get("CEDA_ACCESS_TOKEN")

    if from_local:
        start, end_ts, clipped_end = _date_bounds(start_year, end)
        start_text = start.strftime("%Y-%m-%d")
        end_text = clipped_end.strftime("%Y-%m-%d")
        rows: list[dict[str, object]] = []
        source_label = "midas_open_local"

        with from_local.open(newline="") as handle:
            for row in csv.DictReader(handle):
                if str(row["src_id"]).lstrip("0") != SRC_ID:
                    continue
                day_text = row["ob_end_time"][:10]
                if day_text < start_text or day_text > end_text:
                    continue
                if row.get("source"):
                    source_label = row["source"]
                rows.append(
                    {
                        "ob_end_time": row["ob_end_time"],
                        "mean_wind_speed": row["mean_wind_speed"],
                        "mean_wind_dir": row["mean_wind_dir"],
                    }
                )

        if not rows:
            raise RuntimeError(
                f"No Battersea hourly rows found in {from_local} "
                f"for {start_text} to {end_text}."
            )

        hourly = pd.DataFrame(rows)
        hourly["ob_end_time"] = pd.to_datetime(hourly["ob_end_time"], errors="coerce")
        hourly = hourly.dropna(subset=["ob_end_time"])
        hourly = hourly[(hourly["ob_end_time"] >= start) & (hourly["ob_end_time"] <= end_ts)]
        hourly["mean_wind_speed"] = pd.to_numeric(hourly["mean_wind_speed"], errors="coerce")
        hourly["mean_wind_dir"] = pd.to_numeric(hourly["mean_wind_dir"], errors="coerce")
        hourly = hourly.sort_values("ob_end_time").reset_index(drop=True)
    else:
        hourly, source_label = _fetch_battersea_hourly(
            start_year=start_year,
            end_date=end,
            username=username,
            password=password,
            access_token=access_token,
            dataset_version=dataset_version,
        )

    hourly["station_name"] = STATION_NAME
    hourly["src_id"] = SRC_ID
    hourly["source"] = source_label
    hourly["frequency"] = "hourly"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    hourly.to_csv(output_path, index=False)

    print(
        f"Saved {len(hourly):,} hourly rows to {output_path} "
        f"({hourly['ob_end_time'].min()} to {hourly['ob_end_time'].max()})."
    )
    if end > CEDA_END_DATE:
        print(
            f"  Note: MIDAS Open UK mean wind data currently runs through {CEDA_END_DATE}. "
            "Later dates are not available from this source."
        )
    return hourly


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download hourly Battersea wind speed and direction from MIDAS Open."
    )
    parser.add_argument("--start-year", type=int, default=2016)
    parser.add_argument("--end-date", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--from-local",
        type=Path,
        default=None,
        help="Optional hourly MIDAS CSV to filter instead of downloading from CEDA.",
    )
    parser.add_argument("--dataset-version", default=None)
    parser.add_argument("--ceda-username", default=None)
    parser.add_argument("--ceda-password", default=None)
    parser.add_argument("--ceda-token", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    end_date = (
        datetime.strptime(args.end_date, "%Y-%m-%d").date()
        if args.end_date
        else None
    )

    frame = fetch_london_wind_timeseries(
        output_path=args.output,
        start_year=args.start_year,
        end_date=end_date,
        from_local=args.from_local,
        username=args.ceda_username,
        password=args.ceda_password,
        access_token=args.ceda_token,
        dataset_version=args.dataset_version,
    )
    print(frame.head(5).to_string(index=False))
    print("...")
    print(frame.tail(5).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
