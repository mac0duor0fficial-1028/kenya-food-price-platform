INSERT INTO core.dim_product (product_code, product_name, category, measure_type, unit, is_fao_series) VALUES
    ('maize_fao',            'Maize',            'cereal',    'price', NULL, TRUE),
    ('beans',                'Beans',            'pulse',     'price', NULL, FALSE),
    ('livestock_goat_s_fao', 'Goat',             'livestock', 'price', NULL, TRUE),
    ('food_price_index',     'Food price index', 'composite', 'index', 'index', FALSE)
ON CONFLICT (product_code) DO NOTHING;
-- is_fao_series: derived from the "_fao" suffix; confirm meaning in the dataset documentation.
-- unit: set after profiling (check the `currency` column and the Documentation PDF).

INSERT INTO core.dim_source (source_name, source_ref, update_frequency, license) VALUES
    ('World Bank RTFP - Kenya',
     'https://microdata.worldbank.org/catalog/6167',
     'monthly (irregular release day)',
     'See https://microdata.worldbank.org/terms-of-use - confirm before redistribution')
ON CONFLICT (source_name) DO NOTHING;
