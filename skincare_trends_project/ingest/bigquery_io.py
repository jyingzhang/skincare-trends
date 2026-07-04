"""BigQuery helpers for ingest scripts (uses the gcloud `bq` CLI)."""

from __future__ import annotations

import os
import subprocess
import tempfile
from io import StringIO
from pathlib import Path

import duckdb
import pandas as pd

DEFAULT_PROJECT = "skincare-trends-dev"
RAW_DATASET = "raw"
MODEL_DATASET = "skincare_trends"

# Explicit schemas avoid parquet inferring pandas datetimes as INT64 epoch-ns.
RAW_TABLE_SCHEMAS: dict[str, str] = {
    "raw_trends": "date:DATE,ingredient_name:STRING,search_interest:INTEGER,is_anchor:BOOLEAN",
    "raw_product_trends": (
        "date:DATE,product_id:STRING,search_keyword:STRING,"
        "search_interest:INTEGER,is_anchor:BOOLEAN"
    ),
    "raw_product_search_keyword_candidates": (
        "product_id:STRING,product_name:STRING,brand_name:STRING,"
        "review_count_rank:INTEGER,candidate_rank:INTEGER,search_keyword:STRING,"
        "source:STRING,hero_words:STRING,product_type:STRING,generated_at:TIMESTAMP"
    ),
    "raw_product_search_keywords": (
        "product_id:STRING,product_name:STRING,brand_name:STRING,"
        "review_count_rank:INTEGER,search_keyword:STRING,hero_words:STRING,"
        "product_type:STRING,candidate_rank:INTEGER,candidate_source:STRING,"
        "probe_avg_interest:FLOAT,probe_max_interest:FLOAT,"
        "probe_nonzero_weeks:INTEGER,probe_total_weeks:INTEGER,probed_at:TIMESTAMP"
    ),
}


def gcp_project() -> str:
    return os.environ.get("DBT_GCP_PROJECT", DEFAULT_PROJECT)


def raw_table_ref(table_name: str) -> str:
    return f"{gcp_project()}.{RAW_DATASET}.{table_name}"


def model_table_ref(table_name: str) -> str:
    return f"{gcp_project()}.{MODEL_DATASET}.{table_name}"


def ensure_dataset(dataset: str) -> None:
    subprocess.run(
        ["bq", "mk", "--dataset", "--location=US", f"{gcp_project()}:{dataset}"],
        capture_output=True,
        text=True,
        check=False,
    )


def query_dataframe(sql: str) -> pd.DataFrame:
    result = subprocess.run(
        [
            "bq",
            "query",
            f"--project_id={gcp_project()}",
            "--use_legacy_sql=false",
            "--format=csv",
            "--max_rows=1000000",
            sql,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    if not result.stdout.strip():
        return pd.DataFrame()
    return pd.read_csv(StringIO(result.stdout))


def _schema_column_order(schema: str) -> list[str]:
    return [field.split(":", 1)[0] for field in schema.split(",")]


def _prepare_raw_dataframe(df: pd.DataFrame, table: str) -> pd.DataFrame:
    out = df.copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    if "search_interest" in out.columns:
        out["search_interest"] = pd.to_numeric(out["search_interest"], errors="coerce").astype("Int64")
    if "is_anchor" in out.columns:
        out["is_anchor"] = out["is_anchor"].astype(bool)
    if schema := RAW_TABLE_SCHEMAS.get(table):
        columns = _schema_column_order(schema)
        missing = [column for column in columns if column not in out.columns]
        if missing:
            raise ValueError(f"Missing columns for raw.{table}: {missing}")
        # BigQuery CSV load maps columns by position when --schema is set.
        return out[columns]
    return out


def load_dataframe(
    df: pd.DataFrame,
    *,
    dataset: str,
    table: str,
    replace: bool = True,
) -> None:
    if df.empty:
        print(f"No rows to load into {dataset}.{table}.")
        return

    ensure_dataset(dataset)
    target = f"{gcp_project()}:{dataset}.{table}"
    load_df = _prepare_raw_dataframe(df, table) if dataset == RAW_DATASET else df.copy()

    with tempfile.TemporaryDirectory(prefix="skincare_bq_ingest_") as tmp:
        csv_path = Path(tmp) / f"{table}.csv"
        load_df.to_csv(csv_path, index=False)
        cmd = [
            "bq",
            "load",
            "--source_format=CSV",
            "--skip_leading_rows=1",
        ]
        if schema := RAW_TABLE_SCHEMAS.get(table):
            cmd.extend(["--schema", schema])
        if replace:
            cmd.append("--replace")
        cmd.extend([target, str(csv_path)])
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stdout, result.stderr)
            raise RuntimeError(f"bq load failed for {target}")

    print(f"Loaded {len(df):,} rows into {target}.")


def sync_duckdb_raw_to_bigquery(
    duckdb_path: Path,
    *,
    tables: list[str] | None = None,
) -> None:
    """One-time / periodic sync of DuckDB raw tables into the BigQuery raw dataset."""
    default_tables = [
        "raw_trends",
        "raw_product_trends",
        "raw_sephora_products",
        "raw_sephora_reviews",
        "raw_product_review_summaries",
    ]
    tables = tables or default_tables

    con = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        for table in tables:
            exists = con.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'raw' AND table_name = ?
                """,
                [table],
            ).fetchone()[0]
            if not exists:
                print(f"  SKIP raw.{table} (not in DuckDB)")
                continue
            df = con.execute(f"SELECT * FROM raw.{table}").fetchdf()
            load_dataframe(df, dataset=RAW_DATASET, table=table, replace=True)
    finally:
        con.close()
