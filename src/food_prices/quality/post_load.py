"""Post-load validation, lineage update and mart refresh."""

from __future__ import annotations

import json
from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from food_prices import config
from food_prices.quality.raw_checks import DataQualityError


def _scalar(conn: Connection, sql: str, **params):
    return conn.execute(text(sql), params).scalar()


def _check(name: str, severity: str, passed: bool, value=None, detail: str = "") -> dict:
    return {"name": name, "severity": severity, "passed": bool(passed), "value": value, "detail": detail}


def run_checks(conn: Connection, version: date) -> dict:
    checks: list[dict] = []
    p = {"v": version}

    n_fact = _scalar(conn, "SELECT count(*) FROM core.fact_price WHERE source_version = :v", **p)
    lin = conn.execute(
        text("SELECT loaded_rows, long_rows FROM metadata.lineage WHERE source_version = :v"), p
    ).first()
    checks.append(
        _check(
            "row_reconciliation",
            "fail",
            lin is not None and n_fact == lin[0] == lin[1],
            n_fact,
            f"fact={n_fact}, lineage loaded/long={tuple(lin) if lin else None}",
        )
    )

    v = _scalar(
        conn,
        """SELECT count(*) FROM core.fact_price WHERE source_version = :v
                         AND (date_key IS NULL OR market_key IS NULL OR product_key IS NULL
                              OR source_key IS NULL)""",
        **p,
    )
    checks.append(_check("no_null_keys", "fail", v == 0, v))

    v = _scalar(
        conn, "SELECT count(*) FROM core.fact_price WHERE source_version = :v AND county_key IS NULL", **p
    )
    checks.append(_check("markets_have_county", "warn", v == 0, v))

    v = _scalar(
        conn,
        """SELECT count(*) FROM (SELECT 1 FROM core.fact_price
                         WHERE source_version = :v
                         GROUP BY date_key, market_key, product_key, source_key
                         HAVING count(*) > 1) d""",
        **p,
    )
    checks.append(_check("no_duplicates_on_grain", "fail", v == 0, v))

    v = _scalar(
        conn,
        """SELECT count(*) FROM core.fact_price f
                         JOIN core.dim_product pr USING (product_key)
                         WHERE f.source_version = :v AND pr.measure_type = 'price'
                           AND (f.close_price <= 0 OR f.open_price <= 0
                                OR f.high_price <= 0 OR f.low_price <= 0)""",
        **p,
    )
    checks.append(_check("prices_positive", "fail", v == 0, v))

    v = _scalar(
        conn,
        f"""
        WITH med AS (SELECT product_key, percentile_cont(0.5) WITHIN GROUP (ORDER BY close_price) AS m
                     FROM core.fact_price WHERE source_version = :v GROUP BY product_key)
        SELECT count(*) FROM core.fact_price f
        JOIN med USING (product_key) JOIN core.dim_product pr USING (product_key)
        WHERE f.source_version = :v AND pr.measure_type = 'price'
          AND f.close_price > {config.PLAUSIBLE_MULTIPLE_OF_MEDIAN} * med.m""",
        **p,
    )
    checks.append(
        _check(
            "plausible_range",
            "warn",
            v == 0,
            v,
            f"close > {config.PLAUSIBLE_MULTIPLE_OF_MEDIAN}x product median",
        )
    )

    v = _scalar(
        conn,
        """SELECT count(*) FROM core.fact_price WHERE source_version = :v
                         AND (low_price > high_price
                              OR close_price < low_price OR close_price > high_price)""",
        **p,
    )
    total = max(n_fact, 1)
    checks.append(_check("ohlc_ordering", "warn", v == 0, v, f"{v / total:.2%} of rows"))

    rows = conn.execute(
        text("""
        SELECT pr.product_code,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(f.inflation_pct - f.yoy_change_pct_calc))
        FROM core.fact_price f JOIN core.dim_product pr USING (product_key)
        WHERE f.source_version = :v AND f.inflation_pct IS NOT NULL AND f.yoy_change_pct_calc IS NOT NULL
        GROUP BY pr.product_code"""),
        p,
    ).all()
    gaps = {r[0]: float(r[1]) for r in rows}
    worst = max(gaps.values()) if gaps else 0.0
    checks.append(
        _check(
            "inflation_vs_calc_yoy",
            "warn",
            worst <= config.INFLATION_GAP_WARN_PP,
            gaps,
            "median |inflation_pct - yoy_calc| per product (percentage points)",
        )
    )

    latest = _scalar(conn, "SELECT max(date_key) FROM core.fact_price WHERE source_version = :v", **p)
    behind = _scalar(
        conn,
        f"""SELECT :l < (date_trunc('month', current_date)
                               - interval '{config.FRESHNESS_MAX_MONTHS_BEHIND} months')::date""",
        l=latest,
    )
    checks.append(_check("freshness", "warn", not behind, str(latest)))

    m = conn.execute(
        text("""
        SELECT min(trust_score), max(trust_score), min(inflation_pct), max(inflation_pct),
               avg(spatially_interpolated::int), count(DISTINCT market_key), count(DISTINCT date_key)
        FROM core.fact_price WHERE source_version = :v"""),
        p,
    ).first()
    metrics = {
        "trust_min": _f(m[0]),
        "trust_max": _f(m[1]),
        "inflation_min": _f(m[2]),
        "inflation_max": _f(m[3]),
        "share_interpolated": _f(m[4]),
        "n_markets": int(m[5]),
        "n_months": int(m[6]),
    }

    prev = conn.execute(
        text("""SELECT validation_detail -> 'metrics' FROM metadata.lineage
                                WHERE source_version < :v AND validation_detail IS NOT NULL
                                ORDER BY source_version DESC LIMIT 1"""),
        p,
    ).scalar()
    if prev:
        ok = metrics["n_markets"] >= prev.get("n_markets", 0) and metrics["n_months"] >= prev.get(
            "n_months", 0
        )
        checks.append(
            _check(
                "coverage_regression",
                "warn",
                ok,
                metrics["n_markets"],
                f"previous release: markets={prev.get('n_markets')}, months={prev.get('n_months')}",
            )
        )
    return {"checks": checks, "metrics": metrics}


def _f(x):
    return None if x is None else float(x)


def run_post_load_checks(source_version: str | date, engine: Engine | None = None) -> dict:
    """Run checks, store them in metadata.lineage, raise on any blocking failure."""
    engine = engine or config.get_engine()
    version = date.fromisoformat(source_version) if isinstance(source_version, str) else source_version
    with engine.begin() as conn:
        result = run_checks(conn, version)
        failed = [c for c in result["checks"] if not c["passed"] and c["severity"] == "fail"]
        warned = [c for c in result["checks"] if not c["passed"] and c["severity"] == "warn"]
        status = "failed" if failed else ("passed_with_warnings" if warned else "passed")
        conn.execute(
            text("""UPDATE metadata.lineage SET validation_status = :s,
                    validation_detail = CAST(:d AS jsonb) WHERE source_version = :v"""),
            {"s": status, "d": json.dumps(result, default=str), "v": version},
        )
    result["status"] = status
    if failed:
        raise DataQualityError("Post-load checks failed: " + ", ".join(c["name"] for c in failed))
    return result


def refresh_marts(engine: Engine | None = None) -> None:
    engine = engine or config.get_engine()
    with engine.begin() as conn:
        conn.execute(text("REFRESH MATERIALIZED VIEW mart.county_month"))
        conn.execute(text("REFRESH MATERIALIZED VIEW mart.national_month"))
