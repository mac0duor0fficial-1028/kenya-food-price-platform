"""Fail-fast checks on the raw CSV, before any transformation (catches schema drift)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from food_prices import config


class DataQualityError(Exception):
    """Raised when a blocking data-quality check fails."""


def discover_products(columns) -> list[str]:
    return sorted(c[2:] for c in columns if c.startswith("c_"))


def check_frame(df: pd.DataFrame) -> list[str]:
    """Return a list of human-readable problems (empty list = OK). `df` must be read with dtype=str."""
    problems: list[str] = []

    missing = [c for c in config.REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        problems.append(f"Missing required columns: {missing}")

    products = discover_products(df.columns)
    if set(products) != set(config.EXPECTED_PRODUCTS):
        problems.append(f"Product set changed: found {products}, expected {sorted(config.EXPECTED_PRODUCTS)}")
    measure_cols: list[str] = []
    for p in products:
        for prefix in config.MEASURE_PREFIXES:
            col = f"{prefix}_{p}"
            if col not in df.columns:
                problems.append(f"Missing measure column: {col}")
            else:
                measure_cols.append(col)
    if problems:  # structural problems: stop before touching values
        return problems

    # Grain: one row per market per month, no null keys.
    for col in ("geo_id", "DATES"):
        n = int(df[col].isna().sum())
        if n:
            problems.append(f"{n} null values in key column {col}")
    dates = pd.to_datetime(df["DATES"], format="%Y-%m-%d", errors="coerce")
    bad_dates = int(dates.isna().sum())
    if bad_dates:
        problems.append(f"{bad_dates} unparseable DATES values (expected yyyy-mm-dd)")
    dup = int(df.duplicated(subset=["geo_id", "DATES"]).sum())
    if dup:
        problems.append(f"{dup} duplicate (geo_id, DATES) rows - grain is one row per market-month")

    # year / month must agree with DATES
    y = pd.to_numeric(df["year"], errors="coerce")
    m = pd.to_numeric(df["month"], errors="coerce")
    mismatch = int(((y != dates.dt.year) | (m != dates.dt.month))[dates.notna()].sum())
    if mismatch:
        problems.append(f"{mismatch} rows where year/month disagree with DATES")

    # Numeric columns must parse (a non-numeric string would otherwise be silently lost).
    for col in measure_cols + config.NUMERIC_COLUMNS:
        s = df[col]
        parsed = pd.to_numeric(s, errors="coerce")
        bad = int((parsed.isna() & s.notna()).sum())
        if bad:
            problems.append(f"{bad} non-numeric values in {col}")
    return problems


def run_raw_checks(path: str | Path) -> dict:
    """Read the CSV as text, run all checks, raise DataQualityError on any problem."""
    path = Path(path)
    df = pd.read_csv(path, dtype=str)
    problems = check_frame(df)
    if problems:
        raise DataQualityError(f"{path.name}: " + " | ".join(problems))
    return {"file": path.name, "raw_rows": len(df), "raw_columns": df.shape[1]}
