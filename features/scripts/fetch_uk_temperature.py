#!/usr/bin/env python3
"""
Fetch UK temperature from Met Office HadUK-Grid data.

Daily admin-region temperature (default):
  - One row per date and region with native tasmax and tasmin only.
  - Historical data (2016 through 2025): CEDA HadUK-Grid v1.3.2.ceda admin-region files.

Monthly UK mean temperature (--frequency monthly):
  - Public Met Office UK & regional series (single UK series only).

Usage:
  export CEDA_USERNAME='your_ceda_username'
  export CEDA_PASSWORD='your_ceda_password'
  python features/scripts/fetch_uk_temperature.py

  # London region only:
  python features/scripts/fetch_uk_temperature.py --region London --output data/uk_temperature_london.csv

  # Or local NetCDF files downloaded from CEDA:
  python features/scripts/fetch_uk_temperature.py \\
    --ceda-tasmax-file ~/Downloads/tasmax_hadukgrid_uk_region_day_19310101-20251231.nc \\
    --ceda-tasmin-file ~/Downloads/tasmin_hadukgrid_uk_region_day_19310101-20251231.nc

Register for CEDA (free): https://services.ceda.ac.uk/cedasite/register
"""

from __future__ import annotations

import argparse
import base64
import calendar
import http.cookiejar
import io
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
from typing import Callable

import netCDF4
import numpy as np
import pandas as pd

MET_OFFICE_MONTHLY_URL = (
    "https://www.metoffice.gov.uk/pub/data/weather/uk/climate/datasets/"
    "Tmean/date/UK.txt"
)
CEDA_ARCHIVE_BROWSER = "https://data.ceda.ac.uk"
CEDA_FILE_SERVER = "https://dap.ceda.ac.uk"
CEDA_SIGNIN_URL = "https://auth.ceda.ac.uk/account/signin/"
CEDA_TOKEN_URL = "https://services.ceda.ac.uk/api/token/create/"
CEDA_HADUK_VERSION = "v1.3.2.ceda"
CEDA_HADUK_RELEASE = "v20260512"
FILL_VALUE = 1e20
CEDA_END_DATE = date(2025, 12, 31)


def _is_netcdf(payload: bytes) -> bool:
    return payload.startswith(b"CDF") or payload.startswith(b"\x89HDF")


def _validate_netcdf_payload(payload: bytes, url: str) -> None:
    if _is_netcdf(payload):
        return
    preview = payload[:200].decode("utf-8", errors="replace")
    if preview.lstrip().startswith("<!DOCTYPE") or preview.lstrip().startswith("<html"):
        raise RuntimeError(
            "CEDA returned an HTML page instead of a NetCDF file. "
            "Check your CEDA credentials or access token."
        )
    raise RuntimeError(f"Download from {url} did not return a NetCDF file.")


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


def _build_ceda_downloader(
    username: str | None,
    password: str | None,
    access_token: str | None,
) -> Callable[[str], bytes]:
    if access_token:
        def download_with_token(url: str) -> bytes:
            request = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            with urllib.request.urlopen(request, timeout=300) as response:
                payload = response.read()
            _validate_netcdf_payload(payload, url)
            return payload

        return download_with_token

    if not username or not password:
        raise RuntimeError(
            "CEDA credentials required for daily data from 2016. Set either:\n"
            "  CEDA_ACCESS_TOKEN\n"
            "  CEDA_USERNAME and CEDA_PASSWORD\n"
            "  --ceda-tasmax-file and --ceda-tasmin-file for local NetCDF files\n"
            "Register free at https://services.ceda.ac.uk/cedasite/register"
        )

    token = _try_create_ceda_token(username, password)
    if token:
        def download_with_token(url: str) -> bytes:
            request = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(request, timeout=300) as response:
                payload = response.read()
            _validate_netcdf_payload(payload, url)
            return payload

        return download_with_token

    opener = _create_ceda_session_opener(username, password)

    def download_with_session(url: str) -> bytes:
        with opener.open(url, timeout=300) as response:
            payload = response.read()
        _validate_netcdf_payload(payload, url)
        return payload

    return download_with_session


def _download_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=300) as response:
        return response.read()


def _ceda_region_file_url(variable: str) -> str:
    listing_url = (
        f"{CEDA_ARCHIVE_BROWSER}/badc/ukmo-hadobs/data/insitu/MOHC/HadOBS/"
        f"HadUK-Grid/{CEDA_HADUK_VERSION}/region/{variable}/day/"
        f"{CEDA_HADUK_RELEASE}/?json"
    )
    with urllib.request.urlopen(listing_url, timeout=60) as response:
        listing = json.loads(response.read().decode("utf-8"))

    names = [item["name"] for item in listing.get("items", []) if item.get("name")]
    daily_files = [name for name in names if name.endswith(".nc") and "_day_" in name]
    if not daily_files:
        raise RuntimeError(
            f"No daily {variable} files found in CEDA listing: {listing_url}"
        )
    return (
        f"{CEDA_FILE_SERVER}/badc/ukmo-hadobs/data/insitu/MOHC/HadOBS/"
        f"HadUK-Grid/{CEDA_HADUK_VERSION}/region/{variable}/day/"
        f"{CEDA_HADUK_RELEASE}/{daily_files[0]}?download=1"
    )


def _decode_geo_regions(ds: netCDF4.Dataset) -> list[str]:
    if "geo_region" not in ds.variables:
        return []
    values = ds.variables["geo_region"][:]
    return [str(item).strip() for item in netCDF4.chartostring(values)]


def _time_values_to_dates(time_var) -> list[date]:
    units = getattr(time_var, "units", "days since 1800-01-01 00:00:00")
    if " since " not in units:
        raise ValueError(f"Unsupported time units: {units}")

    step, _, ref = units.partition(" since ")
    ref_dt = datetime.strptime(ref.strip(), "%Y-%m-%d %H:%M:%S")
    offsets = np.asarray(time_var[:], dtype=float)

    if step.startswith("day"):
        deltas = [timedelta(days=float(offset)) for offset in offsets]
    elif step.startswith("hour"):
        deltas = [timedelta(hours=float(offset)) for offset in offsets]
    else:
        raise ValueError(f"Unsupported time units: {units}")

    return [(ref_dt + delta).date() for delta in deltas]


def _extract_all_regions(ds: netCDF4.Dataset, variable: str) -> pd.DataFrame:
    if variable not in ds.variables:
        raise KeyError(f"Variable '{variable}' not found in dataset")

    var = ds.variables[variable]
    dates = pd.to_datetime(_time_values_to_dates(ds.variables["time"]))
    fill_value = getattr(var, "_FillValue", FILL_VALUE)
    regions = _decode_geo_regions(ds)

    if not regions:
        raise ValueError(
            f"Expected admin-region labels in {variable} file, but geo_region was missing."
        )

    data = np.ma.masked_equal(var[:], fill_value)
    if data.ndim != 2 or data.shape[1] != len(regions):
        raise ValueError(f"Unexpected shape for {variable}: {data.shape}")

    records: list[dict] = []
    value_col = f"{variable}_c"
    for region_idx, region in enumerate(regions):
        for day_idx, day in enumerate(dates):
            value = data[day_idx, region_idx]
            if np.ma.is_masked(value):
                continue
            records.append(
                {
                    "date": day,
                    "region": region,
                    value_col: float(value),
                }
            )

    return pd.DataFrame(records)


def _regions_from_netcdf_bytes(payload: bytes, variable: str) -> pd.DataFrame:
    with tempfile.NamedTemporaryFile(suffix=".nc") as tmp:
        tmp.write(payload)
        tmp.flush()
        with netCDF4.Dataset(tmp.name, "r") as ds:
            return _extract_all_regions(ds, variable)


def _regions_from_netcdf_path(path: Path, variable: str) -> pd.DataFrame:
    with netCDF4.Dataset(path, "r") as ds:
        return _extract_all_regions(ds, variable)


def fetch_monthly_uk_temperature(start_year: int = 2016) -> pd.DataFrame:
    """Fetch monthly UK mean temperature from the public Met Office series."""
    raw = _download_bytes(MET_OFFICE_MONTHLY_URL).decode("utf-8")
    lines = raw.splitlines()
    header_idx = next(i for i, line in enumerate(lines) if line.startswith("year"))
    table = pd.read_csv(io.StringIO("\n".join(lines[header_idx:])), sep=r"\s+")

    month_cols = [
        "jan", "feb", "mar", "apr", "may", "jun",
        "jul", "aug", "sep", "oct", "nov", "dec",
    ]
    records: list[dict] = []
    for _, row in table.iterrows():
        year = int(row["year"])
        if year < start_year:
            continue
        for month_idx, col in enumerate(month_cols, start=1):
            value = row[col]
            if pd.isna(value) or value == "---":
                continue
            records.append(
                {
                    "date": date(year, month_idx, 1),
                    "temperature_c": float(value),
                }
            )

    frame = pd.DataFrame(records).sort_values("date").reset_index(drop=True)
    frame["frequency"] = "monthly"
    frame["source"] = "metoffice_uk_regional_series"
    return frame


def _fetch_ceda_historical_by_region(
    start: date,
    end: date,
    download: Callable[[str], bytes] | None = None,
    tasmax_file: Path | None = None,
    tasmin_file: Path | None = None,
) -> pd.DataFrame:
    if tasmax_file and tasmin_file:
        print("Loading local CEDA tasmax archive...")
        tmax = _regions_from_netcdf_path(tasmax_file, "tasmax")
        print("Loading local CEDA tasmin archive...")
        tmin = _regions_from_netcdf_path(tasmin_file, "tasmin")
        source = "ceda_hadukgrid_region_local"
    else:
        if download is None:
            raise RuntimeError("No CEDA download method or local files provided.")
        tmax_url = _ceda_region_file_url("tasmax")
        tmin_url = _ceda_region_file_url("tasmin")
        print("Downloading CEDA tasmax archive...")
        tmax = _regions_from_netcdf_bytes(download(tmax_url), "tasmax")
        print("Downloading CEDA tasmin archive...")
        tmin = _regions_from_netcdf_bytes(download(tmin_url), "tasmin")
        source = "ceda_hadukgrid_region"

    merged = tmax.merge(tmin, on=["date", "region"], how="outer")
    merged = merged[(merged["date"] >= pd.Timestamp(start)) & (merged["date"] <= pd.Timestamp(end))]
    merged["source"] = source
    merged["frequency"] = "daily"
    return merged.sort_values(["date", "region"]).reset_index(drop=True)


def fetch_daily_temperature_by_region(
    start_year: int = 2016,
    end_date: date | None = None,
    username: str | None = None,
    password: str | None = None,
    access_token: str | None = None,
    tasmax_file: Path | None = None,
    tasmin_file: Path | None = None,
) -> pd.DataFrame:
    """Fetch daily temperature for every HadUK-Grid admin region from 2016 onwards."""
    username = username or os.environ.get("CEDA_USERNAME")
    password = password or os.environ.get("CEDA_PASSWORD")
    access_token = access_token or os.environ.get("CEDA_ACCESS_TOKEN")
    end = min(end_date or date.today(), CEDA_END_DATE)
    start = date(start_year, 1, 1)

    if start > end:
        raise RuntimeError(
            f"No CEDA regional data to fetch for {start} to {end}. "
            f"HadUK-Grid admin-region daily files currently run through {CEDA_END_DATE}."
        )

    if tasmax_file and tasmin_file:
        result = _fetch_ceda_historical_by_region(
            start, end, tasmax_file=tasmax_file, tasmin_file=tasmin_file
        )
    else:
        download = _build_ceda_downloader(username, password, access_token)
        result = _fetch_ceda_historical_by_region(start, end, download=download)

    regions = sorted(result["region"].unique())
    print(
        f"Downloaded {len(result):,} daily rows "
        f"({result['date'].min().date()} to {result['date'].max().date()})."
    )
    print(f"  Regions ({len(regions)}): {', '.join(regions)}")

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Met Office HadUK-Grid temperature data."
    )
    parser.add_argument(
        "--frequency",
        choices=("daily", "monthly"),
        default="daily",
        help="Daily admin-region data or monthly UK series. Default: daily.",
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
        help="Last date to include (YYYY-MM-DD). Defaults to latest CEDA data.",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="Optional single admin region to keep (e.g. London). Default: all regions.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "data/uk_temperature_by_region.csv",
        help="Output CSV path (default: data/uk_temperature_by_region.csv).",
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
    parser.add_argument(
        "--ceda-tasmax-file",
        type=Path,
        default=None,
        help="Local HadUK-Grid tasmax NetCDF file downloaded from CEDA.",
    )
    parser.add_argument(
        "--ceda-tasmin-file",
        type=Path,
        default=None,
        help="Local HadUK-Grid tasmin NetCDF file downloaded from CEDA.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    end_date = (
        datetime.strptime(args.end_date, "%Y-%m-%d").date()
        if args.end_date
        else None
    )

    if args.ceda_tasmax_file or args.ceda_tasmin_file:
        if not args.ceda_tasmax_file or not args.ceda_tasmin_file:
            raise SystemExit(
                "Provide both --ceda-tasmax-file and --ceda-tasmin-file."
            )

    if args.frequency == "monthly":
        frame = fetch_monthly_uk_temperature(start_year=args.start_year)
    else:
        frame = fetch_daily_temperature_by_region(
            start_year=args.start_year,
            end_date=end_date,
            username=args.ceda_username,
            password=args.ceda_password,
            access_token=args.ceda_token,
            tasmax_file=args.ceda_tasmax_file,
            tasmin_file=args.ceda_tasmin_file,
        )

    if args.region:
        if args.frequency == "monthly":
            raise SystemExit("--region is only supported with --frequency daily.")
        frame = frame[frame["region"] == args.region].copy()
        if frame.empty:
            raise SystemExit(
                f"No rows found for region '{args.region}'. "
                "Check the exact HadUK-Grid admin region name."
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output, index=False)
    print(f"Saved to {args.output}")
    print(frame.head(5).to_string(index=False))
    print("...")
    print(frame.tail(5).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
