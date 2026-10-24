-- Reporting layer for Grafana. Materialized views are refreshed by the last DAG task.

CREATE MATERIALIZED VIEW IF NOT EXISTS mart.county_month AS
SELECT f.date_key,
       c.county_name,
       p.product_code,
       p.product_name,
       p.measure_type,
       avg(f.close_price)                  AS avg_close,
       avg(f.inflation_pct)                AS avg_inflation_pct,
       avg(f.yoy_change_pct_calc)          AS avg_yoy_calc_pct,
       avg(f.trust_score)                  AS avg_trust,
       avg(f.spatially_interpolated::int)  AS share_interpolated,
       count(DISTINCT f.market_key)        AS n_markets
FROM core.fact_price f
JOIN core.dim_county  c ON c.county_key  = f.county_key
JOIN core.dim_product p ON p.product_key = f.product_key
GROUP BY f.date_key, c.county_name, p.product_code, p.product_name, p.measure_type;

CREATE MATERIALIZED VIEW IF NOT EXISTS mart.national_month AS
SELECT f.date_key,
       p.product_code,
       p.measure_type,
       avg(f.close_price)           AS avg_close,
       avg(f.inflation_pct)         AS avg_inflation_pct,
       avg(f.yoy_change_pct_calc)   AS avg_yoy_calc_pct,
       count(DISTINCT f.market_key) AS n_markets
FROM core.fact_price f
JOIN core.dim_product p ON p.product_key = f.product_key
GROUP BY f.date_key, p.product_code, p.measure_type;

CREATE OR REPLACE VIEW mart.market_coverage AS
SELECT m.market_key,
       m.market_name,
       c.county_name,
       m.lat,
       m.lon,
       count(DISTINCT f.date_key)         AS n_months,
       max(f.date_key)                    AS last_month,
       avg(f.data_coverage_recent)        AS data_coverage_recent,
       avg(f.spatially_interpolated::int) AS share_interpolated
FROM core.fact_price f
JOIN core.dim_market m ON m.market_key = f.market_key
LEFT JOIN core.dim_county c ON c.county_key = m.county_key
GROUP BY m.market_key, m.market_name, c.county_name, m.lat, m.lon;
