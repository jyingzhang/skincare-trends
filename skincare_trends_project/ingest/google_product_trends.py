"""Fetch Google Trends search interest for the top-200 product pilot cohort."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd
from pytrends.request import TrendReq

from bigquery_io import load_dataframe, model_table_ref, query_dataframe

RAW_TABLE = "raw_product_trends"
DEFAULT_CHECKPOINT = (
    Path(__file__).resolve().parent.parent / "data" / "checkpoints" / "raw_product_trends.csv"
)
# Selected from anchor benchmark in analysis/anchor_benchmark_validation_summary.csv
DEFAULT_ANCHOR = "face wash"
DEFAULT_CHUNK_SIZE = 4
DEFAULT_SLEEP_SECONDS = 5.0
DEFAULT_MAX_RETRIES = 4


def fetch_pilot_products(limit: int | None = None) -> pd.DataFrame:
    limit_clause = f"LIMIT {limit}" if limit else ""
    query = f"""
        SELECT
            product_id,
            product_name,
            brand_name,
            search_keyword
        FROM `{model_table_ref('int_pilot_products')}`
        ORDER BY review_count_rank
        {limit_clause}
    """
    return query_dataframe(query)


def build_keyword_map(products: pd.DataFrame) -> dict[str, list[str]]:
    """Map Google Trends keyword -> one or more product_ids."""
    keyword_map: dict[str, list[str]] = {}
    for row in products.itertuples(index=False):
        keyword_map.setdefault(row.search_keyword, []).append(row.product_id)

    shared = {kw: ids for kw, ids in keyword_map.items() if len(ids) > 1}
    if shared:
        print(f"Note: {len(shared)} keywords shared across multiple products (e.g. mini/full size).")
    return keyword_map


def fetch_chunk_with_retry(
    pytrends: TrendReq,
    kw_list: list[str],
    *,
    timeframe: str,
    geo: str,
    max_retries: int,
    sleep_seconds: float,
) -> pd.DataFrame:
    for attempt in range(1, max_retries + 1):
        try:
            pytrends.build_payload(
                kw_list,
                cat=0,
                timeframe=timeframe,
                geo=geo,
                gprop="",
            )
            df = pytrends.interest_over_time()
            if df.empty:
                return pd.DataFrame()

            if "isPartial" in df.columns:
                df = df.drop(columns=["isPartial"])

            return pd.melt(
                df.reset_index(),
                id_vars=["date"],
                value_vars=kw_list,
                var_name="search_keyword",
                value_name="search_interest",
            )
        except Exception as exc:
            message = str(exc)
            if "429" in message and attempt < max_retries:
                wait = sleep_seconds * attempt * 2
                print(f"  Rate limited (429). Waiting {wait:.0f}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(wait)
                continue
            raise

    return pd.DataFrame()


def load_checkpoint(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if df.empty:
        return df
    return df.assign(date=pd.to_datetime(df["date"]))


def save_checkpoint(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out.to_csv(path, index=False)
    keywords = out["search_keyword"].nunique()
    print(f"  Checkpoint saved: {len(out):,} rows, {keywords} keywords -> {path}")


def fetch_google_trends(
    keywords: list[str],
    *,
    anchor: str | None,
    chunk_size: int,
    sleep_seconds: float,
    max_retries: int,
    timeframe: str,
    geo: str,
    keyword_map: dict[str, list[str]],
    checkpoint_path: Path | None = None,
    resume: bool = False,
) -> pd.DataFrame:
    pytrends = TrendReq(hl="en-US", tz=300)

    if anchor and anchor in keywords:
        keywords = [kw for kw in keywords if kw != anchor]

    checkpoint_df = load_checkpoint(checkpoint_path) if resume and checkpoint_path else pd.DataFrame()
    fetched_keywords: set[str] = set()
    if not checkpoint_df.empty:
        fetched_keywords = set(checkpoint_df["search_keyword"].dropna().unique())
        print(
            f"Resuming from checkpoint: {len(checkpoint_df):,} rows, "
            f"{len(fetched_keywords)} keywords already fetched."
        )

    pending_keywords = [kw for kw in keywords if kw not in fetched_keywords]
    all_data: list[pd.DataFrame] = []
    if not checkpoint_df.empty:
        all_data.append(checkpoint_df)

    total_chunks = (len(pending_keywords) + chunk_size - 1) // chunk_size
    if not pending_keywords:
        print("All keywords already present in checkpoint.")
    elif fetched_keywords:
        print(f"Fetching remaining {len(pending_keywords)} keywords in {total_chunks} chunks...")

    for index in range(0, len(pending_keywords), chunk_size):
        chunk = pending_keywords[index : index + chunk_size]
        kw_list = ([anchor] + chunk) if anchor else chunk
        chunk_num = index // chunk_size + 1
        print(f"Fetching chunk {chunk_num}/{total_chunks}: {kw_list}")

        try:
            melted_df = fetch_chunk_with_retry(
                pytrends,
                kw_list,
                timeframe=timeframe,
                geo=geo,
                max_retries=max_retries,
                sleep_seconds=sleep_seconds,
            )
        except Exception as exc:
            print(f"  Error fetching {kw_list}: {exc}")
            continue

        if melted_df.empty:
            print(f"  Warning: No data returned for {kw_list}")
            continue

        melted_df["is_anchor"] = (melted_df["search_keyword"] == anchor) if anchor else False
        chunk_with_ids = attach_product_ids(melted_df, keyword_map)
        all_data.append(chunk_with_ids)

        if checkpoint_path is not None:
            save_checkpoint(pd.concat(all_data, ignore_index=True), checkpoint_path)

        if sleep_seconds:
            time.sleep(sleep_seconds)

    if not all_data:
        return pd.DataFrame()

    final_df = pd.concat(all_data, ignore_index=True)
    return final_df.drop_duplicates(subset=["date", "search_keyword", "product_id"])


def attach_product_ids(
    trends_df: pd.DataFrame,
    keyword_map: dict[str, list[str]],
) -> pd.DataFrame:
    rows: list[dict] = []
    for record in trends_df.to_dict("records"):
        if record["is_anchor"]:
            rows.append({**record, "product_id": None})
            continue

        product_ids = keyword_map.get(record["search_keyword"], [])
        if not product_ids:
            rows.append({**record, "product_id": None})
            continue

        for product_id in product_ids:
            rows.append({**record, "product_id": product_id})

    return pd.DataFrame(rows)


def load_to_bigquery(df: pd.DataFrame) -> None:
    if df.empty:
        print("No trends data to load.")
        return

    load_dataframe(
        df.assign(date=pd.to_datetime(df["date"])),
        dataset="raw",
        table=RAW_TABLE,
        replace=True,
    )
    product_count = df["product_id"].nunique(dropna=True)
    print(f"Loaded {len(df):,} rows for {product_count} products into raw.{RAW_TABLE}.")


def run(
    *,
    limit: int | None,
    anchor: str | None,
    chunk_size: int,
    sleep_seconds: float,
    max_retries: int,
    timeframe: str,
    geo: str,
    checkpoint_path: Path | None,
    resume: bool,
    load_only: bool,
    clear_checkpoint: bool,
) -> None:
    if load_only:
        if checkpoint_path is None or not checkpoint_path.exists():
            raise SystemExit(f"No checkpoint found at {checkpoint_path}. Nothing to load.")
        trends_df = load_checkpoint(checkpoint_path)
        if trends_df.empty:
            raise SystemExit("Checkpoint is empty.")
        print(f"Loading {len(trends_df):,} checkpoint rows into BigQuery...")
        load_to_bigquery(trends_df)
        if clear_checkpoint:
            checkpoint_path.unlink(missing_ok=True)
            print("Checkpoint cleared.")
        return

    products = fetch_pilot_products(limit=limit)
    if products.empty:
        raise SystemExit("No rows found in int_pilot_products.")

    keyword_map = build_keyword_map(products)
    keywords = products["search_keyword"].drop_duplicates().tolist()
    anchor_desc = f"anchor={anchor!r}" if anchor else "anchorless (self-scaled per product)"
    print(
        f"Fetching trends for {len(products)} pilot products "
        f"({len(keywords)} unique keywords, {anchor_desc})."
    )

    trends_df = fetch_google_trends(
        keywords,
        anchor=anchor,
        chunk_size=chunk_size,
        sleep_seconds=sleep_seconds,
        max_retries=max_retries,
        timeframe=timeframe,
        geo=geo,
        keyword_map=keyword_map,
        checkpoint_path=checkpoint_path,
        resume=resume,
    )
    if trends_df.empty:
        raise SystemExit("Google Trends returned no data.")

    load_to_bigquery(trends_df)
    if clear_checkpoint and checkpoint_path is not None:
        checkpoint_path.unlink(missing_ok=True)
        print("Checkpoint cleared after successful load.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Fetch trends for the first N pilot products only (for testing)",
    )
    parser.add_argument(
        "--anchor",
        default=DEFAULT_ANCHOR,
        help=f"Anchor keyword for cross-batch normalization (default: {DEFAULT_ANCHOR})",
    )
    parser.add_argument(
        "--no-anchor",
        action="store_true",
        help=(
            "Anchorless mode: fetch one keyword per request so each product is "
            "self-scaled 0-100 (forces chunk-size=1). Preserves low-volume signal "
            "but drops cross-product absolute comparability."
        ),
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="Keywords per API request, excluding anchor (max 4)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=DEFAULT_SLEEP_SECONDS,
        help="Seconds to wait between API calls",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Retries per chunk when Google rate-limits (429)",
    )
    parser.add_argument(
        "--timeframe",
        default="today 12-m",
        help="Google Trends timeframe (default: today 12-m)",
    )
    parser.add_argument(
        "--geo",
        default="US",
        help="Google Trends geo (default: US)",
    )
    parser.add_argument(
        "--checkpoint",
        default=str(DEFAULT_CHECKPOINT),
        help="CSV checkpoint path (saved after each chunk)",
    )
    parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Disable checkpoint writes",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip keywords already present in the checkpoint",
    )
    parser.add_argument(
        "--load-only",
        action="store_true",
        help="Load checkpoint CSV to BigQuery without fetching",
    )
    parser.add_argument(
        "--clear-checkpoint",
        action="store_true",
        help="Delete checkpoint after a successful BigQuery load",
    )
    args = parser.parse_args()

    if args.chunk_size > 4:
        raise SystemExit("chunk-size must be <= 4 (Google allows 5 keywords including anchor).")

    anchor = None if args.no_anchor else args.anchor
    # Self-scaling requires exactly one keyword per request.
    chunk_size = 1 if args.no_anchor else args.chunk_size

    checkpoint_path = None if args.no_checkpoint else Path(args.checkpoint)

    run(
        limit=args.limit,
        anchor=anchor,
        chunk_size=chunk_size,
        sleep_seconds=args.sleep,
        max_retries=args.max_retries,
        timeframe=args.timeframe,
        geo=args.geo,
        checkpoint_path=checkpoint_path,
        resume=args.resume,
        load_only=args.load_only,
        clear_checkpoint=args.clear_checkpoint,
    )


if __name__ == "__main__":
    main()
