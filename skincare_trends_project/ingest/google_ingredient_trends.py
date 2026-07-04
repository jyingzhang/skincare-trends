"""Fetch Google Trends search interest for top skincare ingredients."""

from __future__ import annotations

import argparse
import random
import time

import pandas as pd
from pytrends.request import TrendReq

from bigquery_io import load_dataframe, model_table_ref, query_dataframe

RAW_TABLE = "raw_trends"
INGREDIENT_CANDIDATE_TABLE = "int_ingredient_trends_cohort"
DEFAULT_ANCHOR = "retinol"
DEFAULT_LIMIT = 100
DEFAULT_CHUNK_SIZE = 2
DEFAULT_SLEEP_SECONDS = 12.0
DEFAULT_MAX_RETRIES = 6
DEFAULT_RATE_LIMIT_BASE_SECONDS = 45.0
DEFAULT_TIMEFRAME = "today 12-m"
DEFAULT_GEO = "US"


def fetch_top_ingredients(limit: int = DEFAULT_LIMIT) -> pd.DataFrame:
    """Return canonical join keys plus Google Trends search terms.

    Uses ingredient_name_raw (e.g. "hyaluronic acid", "ascorbic acid").
    commonly_known_as is a display label and may list multiple aliases separated
    by commas ("Vitamin C, Antioxidant") — not valid as a single Trends query.
    """
    limit_clause = f"LIMIT {limit}" if limit else ""
    query = f"""
        SELECT
            ingredient_name,
            search_keyword
        FROM `{model_table_ref(INGREDIENT_CANDIDATE_TABLE)}`
        WHERE ingredient_name IS NOT NULL
            AND NULLIF(TRIM(search_keyword), '') IS NOT NULL
        ORDER BY trend_rank
        {limit_clause}
    """
    return query_dataframe(query)


def _is_rate_limit_error(exc: Exception) -> bool:
    return "429" in str(exc)


def _backoff_seconds(attempt: int, *, rate_limited: bool) -> float:
    base = DEFAULT_RATE_LIMIT_BASE_SECONDS if rate_limited else 2.0
    return base * (2 ** (attempt - 1)) + random.uniform(2.0, 8.0)


def _new_pytrends() -> TrendReq:
    # Do not pass retries= — pytrends uses urllib3 Retry(method_whitelist=...)
    # which breaks on urllib3 2.x. We handle retries in fetch_chunk_with_retry.
    return TrendReq(hl="en-US", tz=300)


def fetch_chunk_with_retry(
    pytrends: TrendReq,
    kw_list: list[str],
    *,
    timeframe: str,
    geo: str,
    max_retries: int,
) -> tuple[pd.DataFrame, TrendReq]:
    for attempt in range(1, max_retries + 1):
        try:
            pytrends.build_payload(kw_list, cat=0, timeframe=timeframe, geo=geo, gprop="")
            df = pytrends.interest_over_time()
            if df.empty:
                return pd.DataFrame(), pytrends

            if "isPartial" in df.columns:
                df = df.drop(columns=["isPartial"])

            melted_df = pd.melt(
                df.reset_index(),
                id_vars=["date"],
                value_vars=kw_list,
                var_name="search_keyword",
                value_name="search_interest",
            )
            return melted_df, pytrends
        except Exception as exc:
            rate_limited = _is_rate_limit_error(exc)
            wait_seconds = _backoff_seconds(attempt, rate_limited=rate_limited)
            print(f"Error fetching {kw_list} (attempt {attempt}/{max_retries}): {exc}")
            if attempt < max_retries:
                if rate_limited:
                    print(f"Rate limited — waiting {wait_seconds:.0f}s and opening a fresh session...")
                    time.sleep(wait_seconds)
                    pytrends = _new_pytrends()
                else:
                    print(f"Retrying in {wait_seconds:.1f}s...")
                    time.sleep(wait_seconds)
            else:
                raise

    return pd.DataFrame(), pytrends


def _finalize_chunk(
    melted_df: pd.DataFrame,
    *,
    anchor: str | None,
    keyword_to_canonical: dict[str, str],
) -> pd.DataFrame:
    melted_df = melted_df.copy()
    melted_df["is_anchor"] = (melted_df["search_keyword"] == anchor) if anchor else False
    melted_df["ingredient_name"] = melted_df["search_keyword"].map(
        lambda keyword: keyword_to_canonical.get(keyword, keyword)
    )
    return melted_df.drop(columns=["search_keyword"])


def _fetch_chunk_or_split(
    pytrends: TrendReq,
    chunk: list[str],
    *,
    anchor: str | None,
    keyword_to_canonical: dict[str, str],
    timeframe: str,
    geo: str,
    max_retries: int,
    sleep_seconds: float,
) -> tuple[pd.DataFrame, TrendReq]:
    kw_list = [anchor, *chunk] if anchor else list(chunk)
    try:
        melted_df, pytrends = fetch_chunk_with_retry(
            pytrends,
            kw_list,
            timeframe=timeframe,
            geo=geo,
            max_retries=max_retries,
        )
        if melted_df.empty:
            print(f"Warning: No data returned for {kw_list}")
            return pd.DataFrame(), pytrends
        return _finalize_chunk(
            melted_df,
            anchor=anchor,
            keyword_to_canonical=keyword_to_canonical,
        ), pytrends
    except Exception:
        if len(chunk) == 1:
            print(f"Skipping keyword after retries: {chunk[0]!r}")
            return pd.DataFrame(), _new_pytrends()

    print(f"Chunk failed — retrying keywords individually: {chunk}")
    frames: list[pd.DataFrame] = []
    pytrends = _new_pytrends()
    for keyword in chunk:
        if sleep_seconds:
            time.sleep(sleep_seconds)
        single_kw_list = [anchor, keyword] if anchor else [keyword]
        try:
            melted_df, pytrends = fetch_chunk_with_retry(
                pytrends,
                single_kw_list,
                timeframe=timeframe,
                geo=geo,
                max_retries=max_retries,
            )
        except Exception:
            print(f"Skipping keyword after retries: {keyword!r}")
            pytrends = _new_pytrends()
            continue

        if melted_df.empty:
            print(f"Warning: No data returned for {single_kw_list}")
            continue

        frames.append(
            _finalize_chunk(
                melted_df,
                anchor=anchor,
                keyword_to_canonical=keyword_to_canonical,
            )
        )

    if not frames:
        return pd.DataFrame(), pytrends
    return pd.concat(frames, ignore_index=True), pytrends


def fetch_google_trends(
    ingredient_df: pd.DataFrame,
    *,
    anchor: str | None,
    chunk_size: int,
    sleep_seconds: float,
    max_retries: int,
    timeframe: str,
    geo: str,
) -> pd.DataFrame:
    pytrends = _new_pytrends()

    keyword_to_canonical = dict(
        zip(ingredient_df["search_keyword"], ingredient_df["ingredient_name"])
    )
    search_keywords = ingredient_df["search_keyword"].tolist()

    if anchor and anchor in search_keywords:
        search_keywords = [keyword for keyword in search_keywords if keyword != anchor]

    all_data: list[pd.DataFrame] = []
    total_chunks = (len(search_keywords) + chunk_size - 1) // chunk_size

    for index in range(0, len(search_keywords), chunk_size):
        chunk = search_keywords[index : index + chunk_size]
        chunk_num = index // chunk_size + 1
        kw_preview = [anchor, *chunk] if anchor else chunk
        print(f"Fetching chunk {chunk_num}/{total_chunks}: {kw_preview}")

        chunk_df, pytrends = _fetch_chunk_or_split(
            pytrends,
            chunk,
            anchor=anchor,
            keyword_to_canonical=keyword_to_canonical,
            timeframe=timeframe,
            geo=geo,
            max_retries=max_retries,
            sleep_seconds=sleep_seconds,
        )
        if not chunk_df.empty:
            all_data.append(chunk_df)

        if sleep_seconds:
            time.sleep(sleep_seconds)

    if not all_data:
        return pd.DataFrame()

    final_df = pd.concat(all_data, ignore_index=True)
    return final_df.drop_duplicates(subset=["date", "ingredient_name"])


def load_to_bigquery(df: pd.DataFrame) -> None:
    if df.empty:
        print("DataFrame is empty, nothing to load.")
        return

    print(f"Writing to raw.{RAW_TABLE}...")
    load_df = df.assign(date=pd.to_datetime(df["date"]))
    load_dataframe(
        load_df,
        dataset="raw",
        table=RAW_TABLE,
        replace=True,
    )
    print(f"Success! {len(df):,} rows loaded into raw.{RAW_TABLE}.")


def run(
    *,
    limit: int,
    anchor: str | None,
    chunk_size: int,
    sleep_seconds: float,
    max_retries: int,
    timeframe: str,
    geo: str,
) -> None:
    ingredient_df = fetch_top_ingredients(limit=limit)
    anchor_desc = f"anchor={anchor!r}" if anchor else "anchorless (self-scaled per ingredient)"
    print(
        f"Found {len(ingredient_df)} ingredients to track ({anchor_desc}). "
        "Using search_keyword for Google Trends queries."
    )
    trends_df = fetch_google_trends(
        ingredient_df,
        anchor=anchor,
        chunk_size=chunk_size,
        sleep_seconds=sleep_seconds,
        max_retries=max_retries,
        timeframe=timeframe,
        geo=geo,
    )
    load_to_bigquery(trends_df)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--anchor",
        default=DEFAULT_ANCHOR,
        help=f"Anchor keyword for cross-batch normalization (default: {DEFAULT_ANCHOR})",
    )
    parser.add_argument(
        "--no-anchor",
        action="store_true",
        help=(
            "Anchorless mode: fetch one ingredient per request so each is self-scaled "
            "0-100 (forces chunk-size=1). Preserves low-volume signal but drops "
            "cross-ingredient absolute comparability."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Top N ingredients by product_count (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="Ingredients per API request, excluding anchor (max 4)",
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
        default=DEFAULT_TIMEFRAME,
        help=f"Google Trends timeframe (default: {DEFAULT_TIMEFRAME})",
    )
    parser.add_argument(
        "--geo",
        default=DEFAULT_GEO,
        help=f"Google Trends geo (default: {DEFAULT_GEO})",
    )
    args = parser.parse_args()

    if args.chunk_size > 4:
        raise SystemExit("chunk-size must be <= 4 (Google allows 5 keywords including anchor).")
    if args.limit <= 0:
        raise SystemExit("limit must be > 0")

    anchor = None if args.no_anchor else args.anchor
    # Self-scaling requires exactly one keyword per request.
    chunk_size = 1 if args.no_anchor else args.chunk_size

    run(
        limit=args.limit,
        anchor=anchor,
        chunk_size=chunk_size,
        sleep_seconds=args.sleep,
        max_retries=args.max_retries,
        timeframe=args.timeframe,
        geo=args.geo,
    )


if __name__ == "__main__":
    main()
