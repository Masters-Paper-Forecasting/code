#!/usr/bin/env python3
"""
Fetch UK mean wind observations from Met Office MIDAS Open (CEDA).

Exports native hourly station wind measurements from 2016 onwards:
  - mean wind speed (knots) and direction (degrees true)
  - maximum gust speed (knots), direction (degrees true), and time (HHMM)

One row per observation time and station across 176 UK Met Office stations.
Writes two CSVs under data/uk_wind/ for you to merge in a notebook:
  - uk_wind_observations.csv  hourly wind measurements (from per-station yearly files)
  - uk_wind_stations.csv      station metadata (from station-metadata.csv)

Usage:
  export CEDA_USERNAME='your_ceda_username'
  export CEDA_PASSWORD='your_ceda_password'
  python features/fetch_uk_wind.py

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
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import pandas as pd

CEDA_ARCHIVE_BROWSER = "https://data.ceda.ac.uk"
CEDA_FILE_SERVER = "https://dap.ceda.ac.uk"
CEDA_SIGNIN_URL = "https://auth.ceda.ac.uk/account/signin/"
CEDA_TOKEN_URL = "https://services.ceda.ac.uk/api/token/create/"
MIDAS_WIND_ROOT = "/badc/ukmo-midas-open/data/uk-mean-wind-obs"
MIDAS_QC_VERSION = "qc-version-1"
CEDA_END_DATE = date(2024, 12, 31)

NATIVE_COLUMNS = [
    "ob_end_time",
    "src_id",
    "ob_hour_count",
    "mean_wind_speed",
    "mean_wind_dir",
    "max_gust_dir",
    "max_gust_speed",
    "max_gust_ctime",
]

STATION_METADATA_COLUMNS = [
    "src_id",
    "station_name",
    "historic_county",
    "station_latitude",
    "station_longitude",
    "station_elevation",
]


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

    thread_local = threading.local()

    def _session_opener() -> urllib.request.OpenerDirector:
        opener = getattr(thread_local, "opener", None)
        if opener is None:
            opener = _create_ceda_session_opener(username, password)
            thread_local.opener = opener
        return opener

    def download_with_session(url: str) -> bytes:
        def fetch() -> bytes:
            with _session_opener().open(url, timeout=300) as response:
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


def _station_metadata_url(dataset_version: str) -> str:
    suffix = dataset_version.replace("dataset-version-", "dv-")
    return (
        f"{CEDA_FILE_SERVER}{MIDAS_WIND_ROOT}/{dataset_version}/"
        f"midas-open_uk-mean-wind-obs_{suffix}_station-metadata.csv?download=1"
    )


def _load_station_metadata(
    dataset_version: str,
    download: Callable[[str], bytes],
) -> pd.DataFrame:
    payload = download(_station_metadata_url(dataset_version))
    rows = _parse_badc_csv(payload.decode("utf-8"))
    frame = pd.DataFrame(rows)
    for col in ("first_year", "last_year"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    for col in ("station_latitude", "station_longitude", "station_elevation"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["src_id"] = frame["src_id"].astype(str).str.lstrip("0").replace("", "0")
    return frame


def _station_folder_name(src_id: str, station_file_name: str) -> str:
    return f"{int(src_id):05d}_{station_file_name}"


def _year_from_filename(filename: str) -> int | None:
    match = re.search(r"_(\d{4})\.csv$", filename)
    return int(match.group(1)) if match else None


def _collect_download_jobs(
    dataset_version: str,
    stations: pd.DataFrame,
    start_year: int,
    end_year: int,
) -> list[dict]:
    county_listing = _fetch_json(f"{CEDA_ARCHIVE_BROWSER}{MIDAS_WIND_ROOT}/{dataset_version}/?json")
    county_paths = {
        item["name"]: item["path"]
        for item in county_listing.get("items", [])
        if item.get("type") == "dir"
    }

    jobs: list[dict] = []
    for _, station in stations.iterrows():
        county = station["historic_county"]
        county_path = county_paths.get(county)
        if not county_path:
            continue

        folder_name = _station_folder_name(station["src_id"], station["station_file_name"])
        county_items = _fetch_json(f"{CEDA_ARCHIVE_BROWSER}{county_path}/?json")["items"]
        station_paths = {
            item["name"]: item["path"]
            for item in county_items
            if item.get("type") == "dir"
        }
        station_path = station_paths.get(folder_name)
        if not station_path:
            continue

        qc_items = _fetch_json(
            f"{CEDA_ARCHIVE_BROWSER}{station_path}/{MIDAS_QC_VERSION}/?json"
        )["items"]
        year_files = {
            _year_from_filename(item["name"]): item
            for item in qc_items
            if item.get("type") == "file" and item["name"].endswith(".csv")
        }

        first_year = max(int(station["first_year"]), start_year)
        last_year = min(int(station["last_year"]), end_year)
        for year in range(first_year, last_year + 1):
            file_item = year_files.get(year)
            if not file_item:
                continue
            jobs.append(
                {
                    "url": file_item["download"],
                    "src_id": station["src_id"],
                    "year": year,
                }
            )
    return jobs


def _parse_wind_file(payload: bytes, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    rows = _parse_badc_csv(payload.decode("utf-8"))
    if not rows:
        return pd.DataFrame(columns=NATIVE_COLUMNS)

    frame = pd.DataFrame(rows)
    keep = [col for col in NATIVE_COLUMNS if col in frame.columns]
    frame = frame[keep].copy()
    frame["ob_end_time"] = pd.to_datetime(frame["ob_end_time"], errors="coerce")
    frame = frame.dropna(subset=["ob_end_time"])
    frame = frame[(frame["ob_end_time"] >= start) & (frame["ob_end_time"] <= end)]

    for col in ("mean_wind_speed", "max_gust_speed"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    for col in ("mean_wind_dir", "max_gust_dir", "ob_hour_count"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["src_id"] = frame["src_id"].astype(str).str.lstrip("0").replace("", "0")
    return frame


OBSERVATION_COLUMNS = [
    *NATIVE_COLUMNS,
    "source",
    "frequency",
]


def fetch_uk_wind_by_station(
    observations_path: Path,
    stations_path: Path,
    start_year: int = 2016,
    end_date: date | None = None,
    username: str | None = None,
    password: str | None = None,
    access_token: str | None = None,
    dataset_version: str | None = None,
    workers: int = 4,
    batch_size: int = 25,
) -> dict:
    """Fetch UK mean wind observations and station metadata as separate CSVs."""
    username = username or os.environ.get("CEDA_USERNAME")
    password = password or os.environ.get("CEDA_PASSWORD")
    access_token = access_token or os.environ.get("CEDA_ACCESS_TOKEN")
    end = min(end_date or date.today(), CEDA_END_DATE)
    start = pd.Timestamp(date(start_year, 1, 1))
    end_ts = pd.Timestamp(datetime.combine(end, datetime.max.time()))

    if start.date() > end:
        raise RuntimeError(
            f"No MIDAS wind data to fetch for {start.date()} to {end}. "
            "MIDAS Open UK mean wind currently runs through 2024."
        )

    dataset_version = dataset_version or _latest_dataset_version()
    print(f"Using MIDAS Open dataset {dataset_version}")

    download = _build_ceda_downloader(username, password, access_token)
    metadata = _load_station_metadata(dataset_version, download)
    active = metadata[
        (metadata["last_year"] >= start_year) & (metadata["first_year"] <= end.year)
    ].copy()
    print(f"Found {len(active)} stations with data in {start_year}-{end.year}")

    jobs = _collect_download_jobs(dataset_version, active, start_year, end.year)
    if not jobs:
        raise RuntimeError("No MIDAS wind files found for the requested period.")

    source_label = f"ceda_midas_open_{dataset_version.replace('dataset-version-', '')}"
    station_info = (
        active[STATION_METADATA_COLUMNS]
        .drop_duplicates("src_id")
        .sort_values("src_id")
        .copy()
    )
    station_info["source"] = source_label
    observations_path.parent.mkdir(parents=True, exist_ok=True)
    if observations_path.exists():
        observations_path.unlink()

    stations_path.parent.mkdir(parents=True, exist_ok=True)
    station_info.to_csv(stations_path, index=False)
    print(f"Saved {len(station_info)} stations to {stations_path}")

    print(f"Downloading {len(jobs)} yearly station files...")
    completed = 0
    row_count = 0
    min_time: pd.Timestamp | None = None
    max_time: pd.Timestamp | None = None
    station_ids: set[str] = set()
    pending_frames: list[pd.DataFrame] = []
    wrote_header = False

    def _flush_batch() -> None:
        nonlocal wrote_header, row_count, min_time, max_time
        if not pending_frames:
            return
        batch = pd.concat(pending_frames, ignore_index=True)
        pending_frames.clear()
        batch["source"] = source_label
        batch["frequency"] = "hourly"
        batch[OBSERVATION_COLUMNS].to_csv(
            observations_path, mode="a", header=not wrote_header, index=False
        )
        wrote_header = True
        row_count += len(batch)
        batch_min = batch["ob_end_time"].min()
        batch_max = batch["ob_end_time"].max()
        min_time = batch_min if min_time is None else min(min_time, batch_min)
        max_time = batch_max if max_time is None else max(max_time, batch_max)
        station_ids.update(batch["src_id"].unique())

    def _download_job(job: dict) -> pd.DataFrame:
        payload = download(job["url"])
        return _parse_wind_file(payload, start, end_ts)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_download_job, job): job for job in jobs}
        for future in as_completed(futures):
            frame = future.result()
            if not frame.empty:
                pending_frames.append(frame)
            completed += 1
            if len(pending_frames) >= batch_size:
                _flush_batch()
            if completed % 100 == 0 or completed == len(jobs):
                print(f"  {completed}/{len(jobs)} files processed")

    _flush_batch()

    if row_count == 0:
        raise RuntimeError("All downloads succeeded but no rows matched the date filter.")

    stations = sorted(station_ids)
    print(
        f"Downloaded {row_count:,} hourly rows "
        f"({min_time} to {max_time})."
    )
    print(f"  Stations ({len(stations)}): {', '.join(stations[:8])}{'...' if len(stations) > 8 else ''}")

    if (end_date or date.today()) > CEDA_END_DATE:
        print("  Note: MIDAS Open UK mean wind data currently runs through 2024.")

    return {
        "row_count": row_count,
        "min_time": min_time,
        "max_time": max_time,
        "station_count": len(stations),
        "observations_path": observations_path,
        "stations_path": stations_path,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Met Office MIDAS Open UK mean wind data."
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=2016,
        help="First year to include (default: 2016).",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Last date to include (YYYY-MM-DD). Defaults to latest MIDAS data.",
    )
    parser.add_argument(
        "--observations-output",
        type=Path,
        default=Path("data/uk_wind/uk_wind_observations.csv"),
        help="Hourly observations CSV (default: data/uk_wind/uk_wind_observations.csv).",
    )
    parser.add_argument(
        "--stations-output",
        type=Path,
        default=Path("data/uk_wind/uk_wind_stations.csv"),
        help="Station metadata CSV (default: data/uk_wind/uk_wind_stations.csv).",
    )
    parser.add_argument(
        "--dataset-version",
        default=None,
        help="MIDAS dataset version folder (default: latest on CEDA).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Parallel download workers (default: 4).",
    )
    parser.add_argument(
        "--ceda-username",
        default=None,
        help="CEDA username (or set CEDA_USERNAME).",
    )
    parser.add_argument(
        "--ceda-password",
        default=None,
        help="CEDA password (or set CEDA_PASSWORD).",
    )
    parser.add_argument(
        "--ceda-token",
        default=None,
        help="CEDA access token (or set CEDA_ACCESS_TOKEN).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    end_date = (
        datetime.strptime(args.end_date, "%Y-%m-%d").date()
        if args.end_date
        else None
    )

    result = fetch_uk_wind_by_station(
        observations_path=args.observations_output,
        stations_path=args.stations_output,
        start_year=args.start_year,
        end_date=end_date,
        username=args.ceda_username,
        password=args.ceda_password,
        access_token=args.ceda_token,
        dataset_version=args.dataset_version,
        workers=args.workers,
    )

    print(f"Saved observations to {result['observations_path']}")
    print(pd.read_csv(args.observations_output, nrows=5).to_string(index=False))
    print(f"\nSaved stations to {result['stations_path']}")
    print(pd.read_csv(args.stations_output).head(5).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
