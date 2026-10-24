# Data dictionary

Source for every fact column is the RTFP CSV unless stated. `<p>` = product code.

## core.fact_price
| Column | Type | Source / rule |
|---|---|---|
| date_key | date | `DATES` (first of month) |
| market_key | int | FK `dim_market`, from `geo_id` |
| county_key | int | FK `dim_county`, from `adm1_name` |
| product_key | int | FK `dim_product`, from the column suffix `<p>` |
| source_key | int | FK `dim_source` (World Bank RTFP - Kenya) |
| open_price, high_price, low_price, close_price | numeric | `o_<p>`, `h_<p>`, `l_<p>`, `c_<p>` (estimates; unit per `dim_product.unit`) |
| inflation_pct | numeric | `inflation_<p>` x `INFLATION_SCALE` |
| trust_score | numeric | `trust_<p>` |
| spatially_interpolated | boolean | `spatially_interpolated` (0/1) |
| index_confidence_score, data_coverage, data_coverage_recent | numeric | same-named columns |
| yoy_change_pct_calc | numeric | computed: close vs close 12 months earlier, percent |
| source_version | date | release date from the file name |
| load_ts | timestamptz | load time |

## Dimensions
| Table | Columns |
|---|---|
| core.dim_date | date_key, year, month, quarter, month_name (generated from loaded months) |
| core.dim_market | market_key, geo_id (unique), market_name (`mkt_name`), subcounty_name (`adm2_name`), county_key, lat, lon, start_dense_data, last_survey_point |
| core.dim_county | county_key, county_name (`adm1_name`), region (optional, filled manually) |
| core.dim_product | product_key, product_code, product_name, category, measure_type (`price`/`index`), unit (fill after profiling), is_fao_series |
| core.dim_source | source_key, source_name, source_ref, update_frequency, license |

## metadata.lineage (one row per release)
dag_run_id, source_url, file_name, source_version (unique), file_sha256, downloaded_at (file modified time), raw_rows, long_rows, loaded_rows, validation_status (`pending`/`passed`/`passed_with_warnings`/`failed`), validation_detail (JSON: every check plus metrics), loaded_at.

## mart
| Object | Content |
|---|---|
| mart.county_month | per county, month, product: avg_close, avg_inflation_pct, avg_yoy_calc_pct, avg_trust, share_interpolated, n_markets |
| mart.national_month | per month, product: avg_close, avg_inflation_pct, avg_yoy_calc_pct, n_markets |
| mart.market_coverage | per market: n_months, last_month, data_coverage_recent, share_interpolated, lat, lon |

## raw
`raw.rtfp_kenya_<yyyymmdd>`: the release as delivered, every column as text.
