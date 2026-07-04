"""Export dbt models (and optional raw tables) from DuckDB to BigQuery.

Runs dbt locally against DuckDB, then loads each relation into BigQuery using
the `bq` CLI and Parquet. This avoids maintaining a separate dbt-bigquery
target while still letting you explore all layers in the BQ console.

Usage:
    python ingest/export_dbt_to_bigquery.py
    python ingest/export_dbt_to_bigquery.py --include-raw
    python ingest/export_dbt_to_bigquery.py --tables int_pilot_products fct_product_trends
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb

from db import connect, duckdb_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DBT_PROJECT = PROJECT_ROOT / "dbt_project"
MANIFEST_PATH = DBT_PROJECT / "target" / "manifest.json"

DEFAULT_PROJECT = "skincare-trends-dev"
DEFAULT_DATASET = "skincare_trends"


def run_dbt_build() -> None:
    dbt = shutil.which("dbt")
    if dbt is None:
        venv_dbt = PROJECT_ROOT.parent / ".venv" / "bin" / "dbt"
        dbt = str(venv_dbt) if venv_dbt.exists() else None
    if dbt is None:
        raise RuntimeError("dbt not found on PATH; activate the project venv first.")

    env = {**os.environ, "DBT_PROFILES_DIR": str(DBT_PROJECT)}
    subprocess.run(
        [dbt, "run"],
        cwd=DBT_PROJECT,
        env=env,
        check=True,
    )


def relation_names_from_manifest() -> list[str]:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"Missing {MANIFEST_PATH}. Run `dbt run` from dbt_project first."
        )

    manifest = json.loads(MANIFEST_PATH.read_text())
    names: list[str] = []
    for node in manifest["nodes"].values():
        if node["resource_type"] in {"model", "seed"}:
            names.append(node["name"])
    return sorted(set(names))


def raw_table_names(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'raw' AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
    ).fetchall()
    return [row[0] for row in rows]


def table_exists(con: duckdb.DuckDBPyConnection, schema: str, table: str) -> bool:
    row = con.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = ? AND table_name = ?
        """,
        [schema, table],
    ).fetchone()
    return bool(row and row[0] > 0)


def export_table(
    con: duckdb.DuckDBPyConnection,
    *,
    schema: str,
    table: str,
    parquet_path: Path,
    project: str,
    dataset: str,
) -> int:
    qualified = f"{schema}.{table}"
    row_count = con.execute(f"SELECT COUNT(*) FROM {qualified}").fetchone()[0]
    con.execute(
        f"COPY (SELECT * FROM {qualified}) TO '{parquet_path}' (FORMAT PARQUET)"
    )

    target = f"{project}:{dataset}.{table}"
    result = subprocess.run(
        [
            "bq",
            "load",
            "--replace",
            "--source_format=PARQUET",
            target,
            str(parquet_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"bq load failed for {target}")

    return int(row_count)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument(
        "--skip-dbt-run",
        action="store_true",
        help="Skip dbt run and export whatever is already in DuckDB.",
    )
    parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Also export raw.* source tables into the same BQ dataset.",
    )
    parser.add_argument(
        "--tables",
        nargs="*",
        help="Optional subset of dbt model/seed names to export.",
    )
    args = parser.parse_args()

    if shutil.which("bq") is None:
        raise RuntimeError("Google Cloud `bq` CLI not found. Install gcloud SDK first.")

    if not args.skip_dbt_run:
        print("Running dbt run against DuckDB...")
        run_dbt_build()

    dbt_tables = args.tables or relation_names_from_manifest()
    print(f"DuckDB path: {duckdb_path()}")
    print(f"BigQuery target: {args.project}.{args.dataset}")
    print(f"Exporting {len(dbt_tables)} dbt relations...")

    con = connect(read_only=True)
    failures: list[str] = []
    skipped: list[str] = []

    with tempfile.TemporaryDirectory(prefix="skincare_bq_export_") as tmp:
        tmpdir = Path(tmp)
        for table in dbt_tables:
            if not table_exists(con, "main", table):
                skipped.append(table)
                print(f"  SKIP main.{table} (not built in DuckDB yet)")
                continue
            parquet_path = tmpdir / f"{table}.parquet"
            try:
                rows = export_table(
                    con,
                    schema="main",
                    table=table,
                    parquet_path=parquet_path,
                    project=args.project,
                    dataset=args.dataset,
                )
                print(f"  OK  main.{table} -> {args.dataset}.{table} ({rows:,} rows)")
            except Exception as exc:  # noqa: BLE001 - collect and report all failures
                failures.append(f"{table}: {exc}")
                print(f"  FAIL main.{table}: {exc}", file=sys.stderr)

        if args.include_raw:
            raw_tables = raw_table_names(con)
            print(f"Exporting {len(raw_tables)} raw tables...")
            for table in raw_tables:
                parquet_path = tmpdir / f"raw_{table}.parquet"
                try:
                    rows = export_table(
                        con,
                        schema="raw",
                        table=table,
                        parquet_path=parquet_path,
                        project=args.project,
                        dataset=args.dataset,
                        # keep raw table names as-is in the same dataset
                    )
                    print(f"  OK  raw.{table} -> {args.dataset}.{table} ({rows:,} rows)")
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"raw.{table}: {exc}")
                    print(f"  FAIL raw.{table}: {exc}", file=sys.stderr)

    if skipped:
        print(f"\nSkipped {len(skipped)} unbuilt relations: {', '.join(skipped)}")

    if failures:
        print("\nSome tables failed to export:", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        sys.exit(1)

    print("\nDone. Query in BigQuery, e.g.:")
    print(f"  SELECT * FROM `{args.project}.{args.dataset}.int_pilot_products` LIMIT 10;")


if __name__ == "__main__":
    main()
