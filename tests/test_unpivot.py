import pandas as pd
import pytest

from food_prices import config
from food_prices.quality.raw_checks import DataQualityError, check_frame, run_raw_checks
from food_prices.transform.rtfp import LONG_COLUMNS, clean, read_raw, to_typed, unpivot


def test_raw_checks_pass_on_sample(sample_csv):
    summary = run_raw_checks(sample_csv)
    assert summary["raw_columns"] == 46 and summary["raw_rows"] == 41


def test_unpivot_shape_and_products(sample_csv):
    raw = to_typed(read_raw(sample_csv))
    long = unpivot(raw)
    assert len(long) == len(raw) * 4
    assert set(long["product_code"]) == set(config.EXPECTED_PRODUCTS)
    row = raw[(raw.geo_id == "KEN-001") & (raw.DATES == "2024-03-01")].iloc[0]
    got = long[(long.geo_id == "KEN-001") & (long.DATES == "2024-03-01") & (long.product_code == "maize_fao")]
    assert got["close_price"].iloc[0] == row["c_maize_fao"]
    assert got["trust_score"].iloc[0] == row["trust_maize_fao"]


def test_unpivot_drops_rows_without_any_price(sample_csv):
    raw = to_typed(read_raw(sample_csv))
    raw.loc[0, ["o_beans", "h_beans", "l_beans", "c_beans"]] = float("nan")
    assert len(unpivot(raw)) == len(raw) * 4 - 1


def test_clean_output_columns(sample_csv):
    long = clean(unpivot(to_typed(read_raw(sample_csv))))
    assert list(long.columns) == LONG_COLUMNS


def test_raw_check_detects_missing_column(sample_csv):
    df = pd.read_csv(sample_csv, dtype=str).drop(columns=["c_maize_fao"])
    assert any("c_maize_fao" in p or "Product set" in p for p in check_frame(df))


def test_raw_check_detects_new_product(sample_csv):
    df = pd.read_csv(sample_csv, dtype=str)
    for pref in config.MEASURE_PREFIXES:
        df[f"{pref}_sorghum"] = "1"
    assert any("Product set changed" in p for p in check_frame(df))


def test_raw_check_detects_duplicates_and_bad_numbers(sample_csv):
    df = pd.read_csv(sample_csv, dtype=str)
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    df.loc[1, "c_beans"] = "abc"
    problems = " | ".join(check_frame(df))
    assert "duplicate" in problems and "non-numeric" in problems


def test_run_raw_checks_raises(tmp_path, sample_csv):
    bad = tmp_path / "bad.csv"
    pd.read_csv(sample_csv, dtype=str).drop(columns=["geo_id"]).to_csv(bad, index=False)
    with pytest.raises(DataQualityError):
        run_raw_checks(bad)
