from food_prices.transform.rtfp import clean, load_county_map, read_raw, to_typed, unpivot


def test_whitespace_is_trimmed_and_name_not_title_cased(sample_csv):
    long = clean(unpivot(to_typed(read_raw(sample_csv))))
    assert set(long["county_name"]) == {"Nairobi", "Turkana"}


def test_county_map_applied(sample_csv, tmp_path):
    m = tmp_path / "map.csv"
    m.write_text("raw_name,clean_name\nTurkana,Turkana County\n")
    long = clean(unpivot(to_typed(read_raw(sample_csv))), load_county_map(m))
    assert "Turkana County" in set(long["county_name"])


def test_missing_or_empty_map_is_noop(tmp_path):
    assert load_county_map(tmp_path / "nope.csv") == {}
    (tmp_path / "e.csv").write_text("raw_name,clean_name\n")
    assert load_county_map(tmp_path / "e.csv") == {}
