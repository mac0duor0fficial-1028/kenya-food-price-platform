-- Star schema. Grain of fact_price: one row per market x product x month (per source).

CREATE TABLE IF NOT EXISTS core.dim_county (
    county_key   SERIAL PRIMARY KEY,
    county_name  TEXT UNIQUE NOT NULL,
    region       TEXT
);

CREATE TABLE IF NOT EXISTS core.dim_market (
    market_key        SERIAL PRIMARY KEY,
    geo_id            TEXT UNIQUE NOT NULL,
    market_name       TEXT,
    subcounty_name    TEXT,
    county_key        INT REFERENCES core.dim_county (county_key),
    lat               NUMERIC(9, 6),
    lon               NUMERIC(9, 6),
    -- types of these two are confirmed during profiling; TEXT is the safe default
    start_dense_data  TEXT,
    last_survey_point TEXT
);

CREATE TABLE IF NOT EXISTS core.dim_product (
    product_key   SERIAL PRIMARY KEY,
    product_code  TEXT UNIQUE NOT NULL,
    product_name  TEXT,
    category      TEXT,
    measure_type  TEXT NOT NULL CHECK (measure_type IN ('price', 'index')),
    unit          TEXT,           -- fill after profiling (do not assume KES/kg)
    is_fao_series BOOLEAN
);

CREATE TABLE IF NOT EXISTS core.dim_source (
    source_key       SERIAL PRIMARY KEY,
    source_name      TEXT UNIQUE NOT NULL,
    source_ref       TEXT,
    update_frequency TEXT,
    license          TEXT
);

CREATE TABLE IF NOT EXISTS core.dim_date (
    date_key   DATE PRIMARY KEY,
    year       INT NOT NULL,
    month      INT NOT NULL,
    quarter    INT NOT NULL,
    month_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS core.fact_price (
    date_key               DATE NOT NULL REFERENCES core.dim_date (date_key),
    market_key             INT  NOT NULL REFERENCES core.dim_market (market_key),
    county_key             INT  REFERENCES core.dim_county (county_key),
    product_key            INT  NOT NULL REFERENCES core.dim_product (product_key),
    source_key             INT  NOT NULL REFERENCES core.dim_source (source_key),
    open_price             NUMERIC,
    high_price             NUMERIC,
    low_price              NUMERIC,
    close_price            NUMERIC,
    inflation_pct          NUMERIC,
    trust_score            NUMERIC,
    spatially_interpolated BOOLEAN,
    index_confidence_score NUMERIC,
    data_coverage          NUMERIC,
    data_coverage_recent   NUMERIC,
    yoy_change_pct_calc    NUMERIC,
    source_version         DATE NOT NULL,
    load_ts                TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date_key, market_key, product_key, source_key)
);

CREATE INDEX IF NOT EXISTS ix_fact_price_product_date ON core.fact_price (product_key, date_key);
CREATE INDEX IF NOT EXISTS ix_fact_price_county_date  ON core.fact_price (county_key, date_key);
