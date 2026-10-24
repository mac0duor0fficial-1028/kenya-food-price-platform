"""Needs PostgreSQL: TEST_WAREHOUSE_URL=postgresql+psycopg2://user:pw@localhost:5432/testdb"""

from sqlalchemy import text

from food_prices.extract.rtfp import find_new_release
from food_prices.load.rtfp import run_load
from food_prices.quality.post_load import refresh_marts, run_post_load_checks
from food_prices.quality.raw_checks import run_raw_checks
from food_prices.transform.rtfp import run_transform


def _counts(engine):
    with engine.connect() as c:
        return {
            "fact": c.execute(text("SELECT count(*) FROM core.fact_price")).scalar(),
            "markets": c.execute(text("SELECT count(*) FROM core.dim_market")).scalar(),
            "counties": c.execute(text("SELECT count(*) FROM core.dim_county")).scalar(),
            "lineage": c.execute(text("SELECT count(*) FROM metadata.lineage")).scalar(),
        }


def test_full_load_twice_is_idempotent(engine, landing):
    assert find_new_release(engine) == landing
    run_raw_checks(landing)
    parquet = run_transform(landing)
    out1 = run_load(parquet, dag_run_id="t1", engine=engine)
    # 41 market-month rows x 4 products
    assert out1["loaded_rows"] == 164
    first = _counts(engine)
    assert first == {"fact": 164, "markets": 3, "counties": 2, "lineage": 1}

    res = run_post_load_checks(out1["source_version"], engine=engine)
    assert res["status"] in {"passed", "passed_with_warnings"}
    refresh_marts(engine)

    # file was archived -> nothing new
    assert not landing.exists()
    assert find_new_release(engine, landing.parent) is None

    # reload the same release again: identical counts, still one lineage row
    (landing.parent / "archive" / landing.name).replace(landing)
    out2 = run_load(parquet, dag_run_id="t2", engine=engine)
    assert out2 == out1
    assert _counts(engine) == first


def test_raw_snapshot_and_lineage(engine, landing):
    parquet = run_transform(landing)
    run_load(parquet, dag_run_id="t1", engine=engine)
    with engine.connect() as c:
        n = c.execute(text("SELECT count(*) FROM raw.rtfp_kenya_20260824")).scalar()
        lin = c.execute(
            text(
                "SELECT raw_rows, long_rows, loaded_rows, dag_run_id, "
                "length(file_sha256) FROM metadata.lineage"
            )
        ).one()
    assert n == 41 and tuple(lin) == (41, 164, 164, "t1", 64)


def test_mart_views_populated(engine, landing):
    out = run_load(run_transform(landing), engine=engine)
    run_post_load_checks(out["source_version"], engine=engine)
    refresh_marts(engine)
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM mart.county_month")).scalar() > 0
        assert c.execute(text("SELECT count(*) FROM mart.national_month")).scalar() > 0
        assert c.execute(text("SELECT count(*) FROM mart.market_coverage")).scalar() == 3
