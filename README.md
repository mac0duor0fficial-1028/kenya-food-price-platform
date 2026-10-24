# Kenya Food Prices & Inflation Data Platform

A reproducible batch pipeline for the World Bank **Monthly food price estimates by product and market (Kenya)** dataset (`KEN_2021_RTFP_v02_M`, https://microdata.worldbank.org/catalog/6167): Airflow orchestration, pandas transform, a PostgreSQL star schema with lineage and data-quality checks, and a Grafana dashboard. Managed with [uv](https://docs.astral.sh/uv/).

> The values are **model-based estimates**, not observed prices. Four series only: beans, maize, goat, and a composite food price index.

Architecture: `docs/architecture.md` - Data model: `docs/data_model.md` - Dictionary: `docs/data_dictionary.md`.

## Prerequisites
Docker with Compose v2, [uv](https://docs.astral.sh/uv/getting-started/installation/), and the source CSV. Read the dataset's terms of use first: https://microdata.worldbank.org/terms-of-use. Download `KEN_RTFP_mkt_2007_<yyyy-mm-dd>.csv` from the catalog's *Get Microdata* page (a login may be required). Do not commit the CSV.

## Implementation order (each step ends with a check)

**1. Environment**
```bash
uv sync                    # creates .venv from uv.lock (run `uv lock` first if uv.lock is missing)
cp .env.example .env       # then change every value; on Linux set AIRFLOW_UID=$(id -u)
uv run pytest              # unit tests (DB tests skip without TEST_WAREHOUSE_URL)
```
Check: tests pass.

**2. Profile the source** (`notebooks/01_profile.ipynb`)
Put the CSV in `data/landing/`, run the notebook, fill in `docs/source_profile.md`. Decide: the price unit (then set `core.dim_product.unit`), whether `inflation_*` is percent or fraction (`INFLATION_SCALE`), and any county spelling variants (`reference/county_name_map.csv`).
Check: every "to confirm" item in the profile is answered.

**3. Start the stack**
```bash
docker compose up -d --build
```
Airflow http://localhost:8080 (user/password from `.env`), Grafana http://localhost:3000, warehouse on `localhost:5433`. The `sql/*.sql` files run automatically on the warehouse's first start.
Check: `docker compose exec warehouse-db psql -U $WH_USER -d $WH_DB -c '\dn'` lists raw, core, mart, metadata.

**4. Run the pipeline as a script first** (no Airflow)
```bash
export WAREHOUSE_URL=postgresql+psycopg2://$WH_USER:$WH_PASSWORD@localhost:5433/$WH_DB
uv run python -m food_prices.run_local --file data/landing/KEN_RTFP_mkt_2007_<date>.csv
```
Prints raw rows, loaded rows and the check status. Check: `metadata.lineage` has one row; `raw_rows` equals the CSV row count; run it twice, counts stay identical. (The CLI does not move the file; the DAG archives it after loading.)

**5. Run through Airflow**
Leave the CSV in `data/landing/`, unpause `food_prices_etl` in the UI and trigger it once. Check: all tasks green; a second trigger short-circuits (nothing new); a corrupted copy of the file fails at `validate_raw`.
Monthly operation: drop the new release into `data/landing/`; the weekly run picks it up. There is no month-by-month backfill, because each release is a full snapshot.

**6. Review data quality**
```sql
SELECT source_version, validation_status, jsonb_pretty(validation_detail) FROM metadata.lineage;
```
Blocking failures (`fail`) stop the DAG; `warn` items are informational.

**7. Dashboard**
Grafana -> Dashboards -> *Food Prices* -> *Kenya Food Prices & Inflation* (provisioned from `grafana/dashboards/food_prices.json`). It answers: maize price trend, county food-price-index inflation, product comparison across counties, reliability, market coverage, freshness. Screenshots go in `docs/screenshots/`; write 5-7 findings in `docs/insights.md`.

## Project commands
```bash
make sync | up | down | test | lint
make init-db                                  # apply sql/ to $WAREHOUSE_URL (local DB)
make load FILE=data/landing/<release>.csv
TEST_WAREHOUSE_URL=postgresql+psycopg2://user:pw@localhost:5432/testdb uv run pytest   # DB tests; DROPS the schemas there
```

## Key design choices
- **Snapshot loads in one transaction.** A release can revise history, so each load replaces the source's facts and writes lineage atomically; a failure leaves the DB untouched.
- **Own YoY** is calculated by month join (not row shift) and cross-checked against the supplied `inflation_*`.
- **Schema-drift guard.** A new/missing column or product stops the run before any load.
- **Airflow is not in `pyproject.toml`.** It is installed in the image against Airflow's constraints file (`docker/airflow/Dockerfile`); tested with Airflow 2.10.5 / Python 3.12.

## Known limitations
- Estimates, four products, county values are unweighted market means.
- Units and the exact inflation definition must be confirmed from the dataset documentation (see `docs/source_profile.md`).
- Automatic download is not implemented: access conditions are unconfirmed, so ingestion is a file drop into `data/landing/`.
- Grafana provisioning and the Docker build were not run in the authoring environment; everything else is covered by tests.

Code: MIT. Data: see the World Bank terms of use.
