"""Shared DuckDB location for ingest scripts (matches dbt_project/profiles.yml default)."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def duckdb_path() -> Path:
    env = os.environ.get("SKINCARE_DUCKDB_PATH")
    if env:
        return Path(env).expanduser().resolve()
    return _PROJECT_ROOT / "warehouse" / "skincare.duckdb"


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    path = duckdb_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


def ensure_raw_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
