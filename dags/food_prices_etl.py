"""Weekly check for a new World Bank RTFP release; loads it when one is found.

Flow: check_source >> validate_raw >> transform >> load >> quality_check >> refresh_marts
The source publishes a full snapshot roughly monthly (irregular day), so the DAG polls weekly and
short-circuits when the landing folder holds nothing new. There is no per-month backfill: trigger
it manually once with the full historical file for the initial load.

Airflow 2.x imports are used. For Airflow 3 replace the first import with
`from airflow.sdk import dag, task` and `get_current_context` with `from airflow.sdk import get_current_context`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.operators.python import get_current_context

log = logging.getLogger(__name__)


def notify_failure(context) -> None:
    """Replace with an email / Slack webhook call."""
    ti = context["task_instance"]
    log.error("Task failed: dag=%s task=%s run=%s", ti.dag_id, ti.task_id, context.get("run_id"))


@dag(
    dag_id="food_prices_etl",
    schedule="@weekly",
    start_date=datetime(2026, 10, 1),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
        "on_failure_callback": notify_failure,
    },
    tags=["food-prices", "worldbank-rtfp"],
)
def food_prices_etl():
    @task.short_circuit
    def check_source() -> bool:
        from food_prices.extract.rtfp import find_new_release

        return find_new_release() is not None  # False => every downstream task is skipped

    @task
    def validate_raw() -> str:
        from food_prices.extract.rtfp import find_new_release
        from food_prices.quality.raw_checks import run_raw_checks

        path = find_new_release()
        if path is None:
            raise RuntimeError("No new release found")
        log.info("raw checks: %s", run_raw_checks(path))
        return str(path)

    @task
    def transform(csv_path: str) -> str:
        from food_prices.transform.rtfp import run_transform

        return run_transform(csv_path)  # a parquet path, never the data itself

    @task
    def load(parquet_path: str) -> dict:
        from food_prices.load.rtfp import run_load

        run_id = get_current_context()["run_id"]
        return run_load(parquet_path, dag_run_id=run_id)

    @task
    def quality_check(load_result: dict) -> str:
        from food_prices.quality.post_load import run_post_load_checks

        return run_post_load_checks(load_result["source_version"])["status"]

    @task
    def refresh_marts(_status: str) -> None:
        from food_prices.quality.post_load import refresh_marts as refresh

        refresh()

    gate = check_source()
    raw_ok = validate_raw()
    gate >> raw_ok  # short-circuit gates the whole chain
    refresh_marts(quality_check(load(transform(raw_ok))))


food_prices_etl()
