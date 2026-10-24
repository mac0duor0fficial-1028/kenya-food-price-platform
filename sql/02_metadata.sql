CREATE TABLE IF NOT EXISTS metadata.lineage (
    lineage_id        BIGSERIAL PRIMARY KEY,
    dag_run_id        TEXT,
    source_url        TEXT,
    file_name         TEXT NOT NULL,
    source_version    DATE NOT NULL UNIQUE,
    file_sha256       TEXT NOT NULL,
    downloaded_at     TIMESTAMPTZ,
    raw_rows          INT,
    long_rows         INT,
    loaded_rows       INT,
    validation_status TEXT,
    validation_detail JSONB,
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
