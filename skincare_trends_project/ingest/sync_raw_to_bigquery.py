"""Sync DuckDB raw tables into the BigQuery raw dataset for dbt --target prod."""

from __future__ import annotations

import argparse

from bigquery_io import sync_duckdb_raw_to_bigquery
from db import duckdb_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tables",
        nargs="*",
        help="Optional raw table names (default: all standard raw tables)",
    )
    args = parser.parse_args()
    print(f"Syncing raw tables from {duckdb_path()} to BigQuery...")
    sync_duckdb_raw_to_bigquery(duckdb_path(), tables=args.tables)


if __name__ == "__main__":
    main()
