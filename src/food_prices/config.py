"""Central configuration: paths, source constants and the database engine."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# --- paths (override with env vars inside Docker) -----------------------------------------
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[2]))
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
LANDING_DIR = DATA_DIR / "landing"
ARCHIVE_DIR = LANDING_DIR / "archive"
STAGING_DIR = DATA_DIR / "staging"
REFERENCE_DIR = Path(os.getenv("REFERENCE_DIR", PROJECT_ROOT / "reference"))
SQL_DIR = Path(os.getenv("SQL_DIR", PROJECT_ROOT / "sql"))

# --- source constants ----------------------------------------------------------------------
SOURCE_NAME = "World Bank RTFP - Kenya"
SOURCE_REF = "https://microdata.worldbank.org/catalog/6167"
FILE_PATTERN = re.compile(r"^KEN_RTFP_mkt_2007_(\d{4}-\d{2}-\d{2})\.csv$")

# Series present in the Kenya file (verified against the catalog data dictionary).
EXPECTED_PRODUCTS = frozenset({"beans", "maize_fao", "livestock_goat_s_fao", "food_price_index"})

# Column prefix -> fact column. Every product has all six: o_/h_/l_/c_/inflation_/trust_<product>
MEASURE_PREFIXES = {
    "o": "open_price",
    "h": "high_price",
    "l": "low_price",
    "c": "close_price",
    "inflation": "inflation_pct",
    "trust": "trust_score",
}

# Non-product columns the pipeline reads.
KEY_COLUMNS = ["geo_id", "mkt_name", "adm1_name", "adm2_name", "DATES", "year", "month"]
NUMERIC_COLUMNS = [
    "lat",
    "lon",
    "data_coverage",
    "data_coverage_recent",
    "index_confidence_score",
    "spatially_interpolated",
]
TEXT_COLUMNS = ["currency", "start_dense_data", "last_survey_point"]
REQUIRED_COLUMNS = KEY_COLUMNS + NUMERIC_COLUMNS + TEXT_COLUMNS

# Set INFLATION_SCALE=100 if profiling shows inflation_* holds fractions (0.12 = 12 %).
INFLATION_SCALE = float(os.getenv("INFLATION_SCALE", "1"))

# Post-load thresholds (warnings only)
PLAUSIBLE_MULTIPLE_OF_MEDIAN = 10.0
INFLATION_GAP_WARN_PP = 10.0
FRESHNESS_MAX_MONTHS_BEHIND = 2


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Warehouse engine from WAREHOUSE_URL, e.g. postgresql+psycopg2://user:pw@host:5432/db."""
    url = os.environ.get("WAREHOUSE_URL")
    if not url:
        raise RuntimeError("WAREHOUSE_URL is not set (see .env.example)")
    return create_engine(url, future=True, pool_pre_ping=True)
