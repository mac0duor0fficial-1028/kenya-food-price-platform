"""Shared fixtures. tests/fixtures/rtfp_sample.csv is SYNTHETIC (3 markets x 14 months, 46 columns
in the real layout); one market has a missing month to exercise the YoY guard."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

FIXTURE = Path(__file__).parent / "fixtures" / "rtfp_sample.csv"


@pytest.fixture()
def sample_csv() -> Path:
    return FIXTURE


@pytest.fixture()
def landing(tmp_path, monkeypatch):
    """Isolated data dirs + a release file named like the real one."""
    from food_prices import config

    data = tmp_path / "data"
    for sub in ("landing/archive", "staging"):
        (data / sub).mkdir(parents=True)
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "LANDING_DIR", data / "landing")
    monkeypatch.setattr(config, "ARCHIVE_DIR", data / "landing" / "archive")
    monkeypatch.setattr(config, "STAGING_DIR", data / "staging")
    dest = data / "landing" / "KEN_RTFP_mkt_2007_2026-08-24.csv"
    shutil.copy(FIXTURE, dest)
    return dest


@pytest.fixture()
def engine():
    """Needs a real PostgreSQL: set TEST_WAREHOUSE_URL (the schemas are dropped and recreated!)."""
    url = os.getenv("TEST_WAREHOUSE_URL")
    if not url:
        pytest.skip("TEST_WAREHOUSE_URL not set")
    eng = create_engine(url, future=True)
    with eng.begin() as conn:
        for s in ("raw", "core", "mart", "metadata"):
            conn.execute(text(f"DROP SCHEMA IF EXISTS {s} CASCADE"))
    from food_prices.run_local import init_schema

    init_schema(eng)
    yield eng
    eng.dispose()
