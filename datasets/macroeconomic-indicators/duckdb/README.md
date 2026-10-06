# Query the CSV release with DuckDB

DuckDB lets you run SQL directly over the repository's CSV files. It does not change or duplicate the canonical files, and no database server or generated database download is required.

## Start

Install DuckDB using the instructions for your operating system at https://duckdb.org/docs/installation/. From the repository root, run:

```sh
duckdb
```

At the DuckDB prompt, load the ready-made views:

```sql
.read datasets/macroeconomic-indicators/duckdb/setup.sql
```

This creates views for the reference tables, all annual and quarterly observation CSV partitions, a joined `research_observations` view, and an `indicator_coverage` summary. Views read the CSVs when queried; they are not copies of the data.

## Try a query

```sql
SELECT country_name, period, value, value_status
FROM research_observations
WHERE wb_code = 'IND'
  AND indicator_code = 'gdp_real_growth_yoy_pct_quarterly'
ORDER BY period;
```

See `examples.sql` for more queries, including dataset coverage and multi-indicator comparisons.

Run the `.read` command from the repository root so the relative CSV paths resolve. If you want a persistent local DuckDB database later, start DuckDB with a filename (for example, `duckdb research.duckdb`) before loading the setup file. That generated file is local and does not replace the reviewed CSV release.

CSV NULL markers (`\\N`) are read as SQL NULL. The sources, methods, licensing notes, and release checks remain documented in the dataset README and source manifest.
