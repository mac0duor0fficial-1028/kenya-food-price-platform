"""Run the whole pipeline without Airflow:

uv run python -m food_prices.run_local --init-schema
uv run python -m food_prices.run_local --file data/landing/KEN_RTFP_mkt_2007_2026-08-24.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy.engine import Engine

from food_prices import config
from food_prices.load.rtfp import run_load
from food_prices.quality.post_load import refresh_marts, run_post_load_checks
from food_prices.quality.raw_checks import run_raw_checks
from food_prices.transform.rtfp import run_transform


def init_schema(engine: Engine | None = None, sql_dir: Path | None = None) -> list[str]:
    """Apply sql/*.sql in filename order (Docker does this automatically via initdb.d)."""
    engine = engine or config.get_engine()
    sql_dir = sql_dir or config.SQL_DIR
    files = sorted(sql_dir.glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"No .sql files in {sql_dir} (set SQL_DIR if the package is installed)")
    applied = []
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        for f in files:
            cur.execute(f.read_text())
            applied.append(f.name)
        raw.commit()
    finally:
        raw.close()
    return applied


def run_pipeline(csv_path: str | Path, engine: Engine | None = None) -> dict:
    engine = engine or config.get_engine()
    raw_summary = run_raw_checks(csv_path)
    parquet = run_transform(csv_path)
    loaded = run_load(parquet, dag_run_id="local", engine=engine)
    checks = run_post_load_checks(loaded["source_version"], engine=engine)
    refresh_marts(engine)
    return {"raw": raw_summary, "load": loaded, "status": checks["status"]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--init-schema", action="store_true", help="apply sql/*.sql first")
    ap.add_argument("--file", help="path to KEN_RTFP_mkt_2007_<date>.csv")
    args = ap.parse_args()
    if not (args.init_schema or args.file):
        ap.error("give --init-schema and/or --file")
    if args.init_schema:
        print("applied:", init_schema())
    if args.file:
        print(json.dumps(run_pipeline(args.file), indent=2))


if __name__ == "__main__":
    main()
