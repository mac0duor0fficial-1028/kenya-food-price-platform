# Source profile: World Bank RTFP, Kenya

| Item | Value |
|---|---|
| Name | Monthly food price estimates by product and market (Kenya) |
| Reference ID | `KEN_2021_RTFP_v02_M` |
| Catalog page | https://microdata.worldbank.org/catalog/6167 |
| Producer | Bo Pieter Johannes Andrée (World Bank, Real-Time Development Indicators) |
| Format | One CSV, **wide**: `KEN_RTFP_mkt_2007_<yyyy-mm-dd>.csv` (the date is the release version) |
| Release seen at design time | 2026-08-24: 55,224 rows x 46 columns, 233 markets, 2007-01 to 2026-08 |
| Update frequency | Monthly, irregular release day (observed 24th and 27th) |
| Grain | One row per market (`geo_id`) per month (`DATES`) |
| Access / licence | **TO CONFIRM**: read the Get Microdata page and https://microdata.worldbank.org/terms-of-use (login? redistribution? citation text?) |

Row counts and the latest month change with every release; never hard-code them.

## Columns (46)
- **Geography:** `ISO3`, `country`, `adm1_name`, `adm2_name`, `mkt_name`, `lat`, `lon`, `geo_id`
- **Time:** `year`, `month`, `DATES`
- **Context/quality:** `currency`, `components`, `start_dense_data`, `last_survey_point`, `data_coverage`, `data_coverage_recent`, `index_confidence_score`, `spatially_interpolated`
- **Bare product columns:** `beans`, `livestock_goat_s_fao`, `maize_fao` (contents TO CONFIRM; the pipeline ignores them)
- **Per product** (`beans`, `livestock_goat_s_fao`, `maize_fao`, `food_price_index`): `o_` open, `h_` high, `l_` low, `c_` close, `inflation_`, `trust_`

## Answers to fill in from `notebooks/01_profile.ipynb`
| Question | Answer |
|---|---|
| Exactly one row per `geo_id` x month? | |
| Distinct `currency` values | |
| Unit of prices (per kg? per head for goat?) | |
| `adm1_name` = counties? Distinct count; spelling variants | |
| Do `start_dense_data`, `last_survey_point`, `data_coverage*` vary by month or only by market? | |
| Contents of bare `beans` / `maize_fao` / `livestock_goat_s_fao` columns | |
| Range of `trust_*`, `index_confidence_score` | |
| Is `inflation_*` year-on-year? Percent or fraction? (set `INFLATION_SCALE=100` if fraction) | |
| Share of `spatially_interpolated = 1`, and trend by year | |
| `low <= open, close <= high` always true? Share violating | |
| Meaning of the `_fao` suffix | |

## Known quirks (confirm)
- Values are **model-based estimates**, not observed prices.
- A new release can restate earlier months (the pipeline replaces the whole snapshot).
- Many cells can be empty where a market has no estimate for a product.
