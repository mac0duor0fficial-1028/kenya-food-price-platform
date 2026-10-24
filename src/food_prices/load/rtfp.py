"""Snapshot-aware, idempotent load of one RTFP release into PostgreSQL (single transaction)."""

from __future__ import annotations

import io
import json
import shutil
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from food_prices import config
from food_prices.transform.rtfp import LONG_COLUMNS

TMP_TABLE = "tmp_long"
_TMP_DDL = f"""
CREATE TEMP TABLE {TMP_TABLE} (
    geo_id text, market_name text, county_name text, subcounty_name text,
    lat numeric, lon numeric, date_key date, currency text,
    start_dense_data text, last_survey_point text,
    data_coverage numeric, data_coverage_recent numeric, index_confidence_score numeric,
    spatially_interpolated boolean, product_code text,
    open_price numeric, high_price numeric, low_price numeric, close_price numeric,
    inflation_pct numeric, trust_score numeric, yoy_change_pct_calc numeric
) ON COMMIT DROP
"""


def _copy_frame(conn: Connection, df: pd.DataFrame, table: str, columns: list[str]) -> None:
    """Bulk-load a DataFrame with COPY on the connection's own transaction (SQLAlchemy 1.4/2.0 safe)."""
    buf = io.StringIO()
    df[columns].to_csv(buf, index=False, header=False)
    buf.seek(0)
    cols = ", ".join(f'"{c}"' for c in columns)
    cur = conn.connection.cursor()
    try:
        cur.copy_expert(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, NULL '')", buf)
    finally:
        cur.close()


def _load_raw_snapshot(conn: Connection, csv_path: Path, version: date) -> str:
    """Keep the untouched CSV (all text) as raw.rtfp_kenya_<yyyymmdd>. One table per release."""
    df = pd.read_csv(csv_path, dtype=str)
    table = f"raw.rtfp_kenya_{version:%Y%m%d}"
    conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
    col_ddl = ", ".join(f'"{c}" text' for c in df.columns)
    conn.execute(text(f"CREATE TABLE {table} ({col_ddl})"))
    _copy_frame(conn, df, table, list(df.columns))
    return table


def _source_key(conn: Connection) -> int:
    row = conn.execute(
        text("SELECT source_key FROM core.dim_source WHERE source_name = :n"),
        {"n": config.SOURCE_NAME},
    ).first()
    if row is None:
        raise RuntimeError("dim_source row missing - did sql/04_seed.sql run?")
    return int(row[0])


def run_load(parquet_path: str | Path, dag_run_id: str | None = None, engine: Engine | None = None) -> dict:
    """Load one release. Everything happens in ONE transaction: any failure leaves the DB untouched."""
    engine = engine or config.get_engine()
    parquet_path = Path(parquet_path)
    meta = json.loads(parquet_path.with_suffix(".meta.json").read_text())
    version = date.fromisoformat(meta["source_version"])
    csv_path = Path(meta["csv_path"])
    long = pd.read_parquet(parquet_path)

    with engine.begin() as conn:
        _load_raw_snapshot(conn, csv_path, version)

        conn.execute(text(_TMP_DDL))
        _copy_frame(conn, long, TMP_TABLE, LONG_COLUMNS)

        conn.execute(
            text(f"""
            INSERT INTO core.dim_county (county_name)
            SELECT DISTINCT county_name FROM {TMP_TABLE} WHERE county_name IS NOT NULL
            ON CONFLICT (county_name) DO NOTHING""")
        )
        # Most recent attributes per market win.
        conn.execute(
            text(f"""
            INSERT INTO core.dim_market
                (geo_id, market_name, subcounty_name, county_key, lat, lon,
                 start_dense_data, last_survey_point)
            SELECT DISTINCT ON (t.geo_id)
                   t.geo_id, t.market_name, t.subcounty_name, c.county_key, t.lat, t.lon,
                   t.start_dense_data, t.last_survey_point
            FROM {TMP_TABLE} t
            LEFT JOIN core.dim_county c ON c.county_name = t.county_name
            ORDER BY t.geo_id, t.date_key DESC
            ON CONFLICT (geo_id) DO UPDATE SET
                market_name = EXCLUDED.market_name, subcounty_name = EXCLUDED.subcounty_name,
                county_key = EXCLUDED.county_key, lat = EXCLUDED.lat, lon = EXCLUDED.lon,
                start_dense_data = EXCLUDED.start_dense_data,
                last_survey_point = EXCLUDED.last_survey_point""")
        )
        conn.execute(
            text(f"""
            INSERT INTO core.dim_date (date_key, year, month, quarter, month_name)
            SELECT d, extract(year FROM d)::int, extract(month FROM d)::int,
                   extract(quarter FROM d)::int, trim(to_char(d, 'Month'))
            FROM (SELECT DISTINCT date_key AS d FROM {TMP_TABLE}) x
            ON CONFLICT (date_key) DO NOTHING""")
        )

        sk = _source_key(conn)
        conn.execute(text("DELETE FROM core.fact_price WHERE source_key = :sk"), {"sk": sk})
        result = conn.execute(
            text(f"""
            INSERT INTO core.fact_price
                (date_key, market_key, county_key, product_key, source_key,
                 open_price, high_price, low_price, close_price, inflation_pct, trust_score,
                 spatially_interpolated, index_confidence_score, data_coverage,
                 data_coverage_recent, yoy_change_pct_calc, source_version)
            SELECT t.date_key, m.market_key, m.county_key, p.product_key, :sk,
                   t.open_price, t.high_price, t.low_price, t.close_price, t.inflation_pct,
                   t.trust_score, t.spatially_interpolated, t.index_confidence_score,
                   t.data_coverage, t.data_coverage_recent, t.yoy_change_pct_calc, :v
            FROM {TMP_TABLE} t
            JOIN core.dim_market  m ON m.geo_id = t.geo_id
            JOIN core.dim_product p ON p.product_code = t.product_code"""),
            {"sk": sk, "v": version},
        )
        loaded = int(result.rowcount)
        if loaded != len(long):  # a join silently dropped rows -> abort and roll back
            raise RuntimeError(f"Loaded {loaded} rows but staging had {len(long)}; rolled back")

        conn.execute(
            text("""
            INSERT INTO metadata.lineage
                (dag_run_id, source_url, file_name, source_version, file_sha256, downloaded_at,
                 raw_rows, long_rows, loaded_rows, validation_status, loaded_at)
            VALUES (:run, :url, :fn, :v, :sha, :dl, :raw, :lng, :loaded, 'pending', now())
            ON CONFLICT (source_version) DO UPDATE SET
                dag_run_id = EXCLUDED.dag_run_id, source_url = EXCLUDED.source_url,
                file_name = EXCLUDED.file_name, file_sha256 = EXCLUDED.file_sha256,
                downloaded_at = EXCLUDED.downloaded_at, raw_rows = EXCLUDED.raw_rows,
                long_rows = EXCLUDED.long_rows, loaded_rows = EXCLUDED.loaded_rows,
                validation_status = 'pending', validation_detail = NULL, loaded_at = now()"""),
            {
                "run": dag_run_id,
                "url": meta["source_url"],
                "fn": meta["file_name"],
                "v": version,
                "sha": meta["file_sha256"],
                "dl": meta["downloaded_at"],
                "raw": meta["raw_rows"],
                "lng": meta["long_rows"],
                "loaded": loaded,
            },
        )

    _archive(csv_path)  # only after a successful commit
    return {"source_version": version.isoformat(), "loaded_rows": loaded}


def _archive(csv_path: Path) -> None:
    if csv_path.exists() and csv_path.parent == config.LANDING_DIR:
        config.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(csv_path), str(config.ARCHIVE_DIR / csv_path.name))
