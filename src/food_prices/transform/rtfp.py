"""Wide -> long transform for the RTFP Kenya file, plus cleaning and YoY."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from food_prices import config
from food_prices.extract.rtfp import file_info
from food_prices.quality.raw_checks import discover_products

PRICE_COLUMNS = ["open_price", "high_price", "low_price", "close_price"]
MEASURE_COLUMNS = PRICE_COLUMNS + ["inflation_pct", "trust_score"]

LONG_COLUMNS = [
    "geo_id",
    "market_name",
    "county_name",
    "subcounty_name",
    "lat",
    "lon",
    "date_key",
    "currency",
    "start_dense_data",
    "last_survey_point",
    "data_coverage",
    "data_coverage_recent",
    "index_confidence_score",
    "spatially_interpolated",
    "product_code",
    "open_price",
    "high_price",
    "low_price",
    "close_price",
    "inflation_pct",
    "trust_score",
    "yoy_change_pct_calc",
]

_ID_COLUMNS = [
    "geo_id",
    "mkt_name",
    "adm1_name",
    "adm2_name",
    "lat",
    "lon",
    "DATES",
    "currency",
    "start_dense_data",
    "last_survey_point",
    "data_coverage",
    "data_coverage_recent",
    "index_confidence_score",
    "spatially_interpolated",
]


def read_raw(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str)


def to_typed(df: pd.DataFrame) -> pd.DataFrame:
    """Parse numeric columns. Raw checks already proved they parse, so errors are not coerced."""
    df = df.copy()
    products = discover_products(df.columns)
    numeric = list(config.NUMERIC_COLUMNS)
    numeric += [f"{pref}_{p}" for p in products for pref in config.MEASURE_PREFIXES]
    for col in numeric:
        df[col] = pd.to_numeric(df[col])
    return df


def unpivot(df: pd.DataFrame) -> pd.DataFrame:
    """One row per market x month x product. Rows with no open/high/low/close are dropped."""
    products = discover_products(df.columns)
    if set(products) != set(config.EXPECTED_PRODUCTS):
        raise ValueError(f"Product set changed: {products}")
    frames = []
    for p in products:
        cols = {f"{pref}_{p}": name for pref, name in config.MEASURE_PREFIXES.items()}
        sub = df[_ID_COLUMNS + list(cols)].rename(columns=cols).assign(product_code=p)
        frames.append(sub)
    long = pd.concat(frames, ignore_index=True)
    return long.dropna(subset=PRICE_COLUMNS, how="all").reset_index(drop=True)


def load_county_map(path: Path | None = None) -> dict[str, str]:
    """reference/county_name_map.csv (raw_name,clean_name). Missing/empty file => no remapping."""
    path = path or (config.REFERENCE_DIR / "county_name_map.csv")
    if not path.exists():
        return {}
    m = pd.read_csv(path, dtype=str).dropna()
    return dict(zip(m["raw_name"].str.strip(), m["clean_name"].str.strip()))


def _clean_names(s: pd.Series, mapping: dict[str, str] | None = None) -> pd.Series:
    # Whitespace only. We deliberately avoid str.title(): it breaks names like Murang'a.
    out = s.astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
    if mapping:
        out = out.replace(mapping)
    return out


def add_yoy(long: pd.DataFrame) -> pd.DataFrame:
    """yoy_change_pct_calc = (close / close exactly 12 calendar months earlier - 1) * 100.

    Implemented as a join on (market, product, month + 12). A row-based shift(12) would pair the
    wrong months whenever a market is missing a month.
    """
    long = long.sort_values(["geo_id", "product_code", "date_key"]).reset_index(drop=True)
    dt = pd.to_datetime(long["date_key"])
    long["_period"] = dt.dt.year * 12 + dt.dt.month
    prev = long[["geo_id", "product_code", "_period", "close_price"]].rename(
        columns={"close_price": "_prev_close"}
    )
    prev["_period"] = prev["_period"] + 12
    long = long.merge(prev, on=["geo_id", "product_code", "_period"], how="left", validate="1:1")
    valid = (long["_prev_close"] > 0) & long["close_price"].notna()
    long["yoy_change_pct_calc"] = ((long["close_price"] / long["_prev_close"] - 1) * 100).where(valid)
    return long.drop(columns=["_period", "_prev_close"])


def clean(long: pd.DataFrame, county_map: dict[str, str] | None = None) -> pd.DataFrame:
    long = long.rename(
        columns={"mkt_name": "market_name", "adm1_name": "county_name", "adm2_name": "subcounty_name"}
    ).copy()
    long["date_key"] = pd.to_datetime(long["DATES"]).dt.date
    long["county_name"] = _clean_names(long["county_name"], county_map)
    long["subcounty_name"] = _clean_names(long["subcounty_name"])
    long["market_name"] = _clean_names(long["market_name"])
    long["geo_id"] = long["geo_id"].astype("string").str.strip()
    long["spatially_interpolated"] = long["spatially_interpolated"].astype("Int64").astype("boolean")
    if config.INFLATION_SCALE != 1:
        long["inflation_pct"] = long["inflation_pct"] * config.INFLATION_SCALE
    long = add_yoy(long)
    return long[LONG_COLUMNS]


def run_transform(csv_path: str | Path, staging_dir: Path | None = None) -> str:
    """CSV -> staging parquet (+ .meta.json sidecar with lineage facts). Returns the parquet path."""
    csv_path = Path(csv_path)
    staging_dir = staging_dir or config.STAGING_DIR
    staging_dir.mkdir(parents=True, exist_ok=True)

    raw = read_raw(csv_path)
    long = clean(unpivot(to_typed(raw)), load_county_map())

    info = file_info(csv_path)
    version = info["source_version"]
    parquet_path = staging_dir / f"rtfp_long_{version}.parquet"
    long.to_parquet(parquet_path, index=False)

    meta = {**info, "raw_rows": int(len(raw)), "long_rows": int(len(long)), "csv_path": str(csv_path)}
    parquet_path.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
    return str(parquet_path)
