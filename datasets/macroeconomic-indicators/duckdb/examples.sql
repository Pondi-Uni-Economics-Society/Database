-- Coverage by indicator and frequency
SELECT * FROM indicator_coverage ORDER BY frequency, indicator_code;

-- India's quarterly real GDP growth
SELECT country_name, period, value, value_status
FROM research_observations
WHERE wb_code = 'IND'
  AND indicator_code = 'gdp_real_growth_yoy_pct_quarterly'
ORDER BY period;

-- Compare annual GDP growth and inflation for India
SELECT period, indicator_code, display_name, value, unit
FROM research_observations
WHERE wb_code = 'IND'
  AND indicator_code IN (
    'gdp_real_growth_yoy_pct_annual',
    'inflation_consumer_prices_yoy_pct_annual_wdi'
  )
ORDER BY period, indicator_code;
