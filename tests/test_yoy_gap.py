import pandas as pd

from food_prices.transform.rtfp import add_yoy, clean, read_raw, to_typed, unpivot


def _expected_yoy(long: pd.DataFrame) -> pd.Series:
    """Independent implementation: join each row to the row exactly 12 calendar months earlier."""
    d = pd.to_datetime(long["date_key"])
    cur = long.assign(period=d.dt.year * 12 + d.dt.month)
    prev = cur[["geo_id", "product_code", "period", "close_price"]].copy()
    prev["period"] += 12
    m = cur.merge(prev, on=["geo_id", "product_code", "period"], how="left", suffixes=("", "_prev"))
    return (m["close_price"] / m["close_price_prev"] - 1) * 100


def test_yoy_matches_independent_calculation(sample_csv):
    long = clean(unpivot(to_typed(read_raw(sample_csv))))
    exp = _expected_yoy(long).reset_index(drop=True)
    got = long["yoy_change_pct_calc"].reset_index(drop=True)
    pd.testing.assert_series_equal(got, exp, check_names=False, rtol=1e-9)


def test_yoy_is_null_in_first_year_and_set_after(sample_csv):
    long = clean(unpivot(to_typed(read_raw(sample_csv))))
    first_year = long[pd.to_datetime(long["date_key"]).dt.year == 2024]
    assert first_year["yoy_change_pct_calc"].isna().all()
    # KEN-002 lacks June 2024, yet Jan-2025 still has a valid base (Jan-2024) 12 months back.
    jan25 = long[(long.date_key.astype(str) == "2025-01-01") & (long.product_code == "maize_fao")]
    assert len(jan25) == 3 and jan25["yoy_change_pct_calc"].notna().all()


def test_yoy_pairs_correct_months_when_a_month_is_missing():
    # Missing 2024-06: a naive shift(12) would pair Mar-25 with Feb-24 (row 13 vs row 1).
    months = [m for m in pd.period_range("2024-01", "2025-03", freq="M") if str(m) != "2024-06"]
    df = pd.DataFrame(
        {
            "geo_id": "A",
            "product_code": "p",
            "date_key": [m.to_timestamp().date() for m in months],
            "close_price": [100.0 + i * 10 for i in range(len(months))],
        }
    )
    out = add_yoy(df).set_index("date_key")
    by_month = {str(k): v for k, v in df.set_index("date_key")["close_price"].items()}
    for cur, base in [("2025-01-01", "2024-01-01"), ("2025-03-01", "2024-03-01")]:
        expected = (by_month[cur] / by_month[base] - 1) * 100
        got = out.loc[pd.Timestamp(cur).date(), "yoy_change_pct_calc"]
        assert abs(got - expected) < 1e-9
    # June 2025 does not exist; July 2025 would have no base -> not in range, so check Jun-24 absent
    assert pd.Timestamp("2024-06-01").date() not in set(out.index)
