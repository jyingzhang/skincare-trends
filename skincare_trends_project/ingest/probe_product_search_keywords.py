"""Probe Google Trends keyword candidates and pick the best search keyword per product."""

from __future__ import annotations

import argparse
import random
import time
from datetime import datetime, timezone

import pandas as pd
from pytrends.request import TrendReq

from bigquery_io import load_dataframe, raw_table_ref, query_dataframe

RAW_CANDIDATES_TABLE = "raw_product_search_keyword_candidates"
RAW_KEYWORDS_TABLE = "raw_product_search_keywords"
DEFAULT_ANCHOR = "face wash"
DEFAULT_SLEEP_SECONDS = 12.0
DEFAULT_MAX_RETRIES = 6
DEFAULT_RATE_LIMIT_BASE_SECONDS = 45.0
DEFAULT_TIMEFRAME = "today 12-m"
DEFAULT_GEO = "US"


def fetch_candidates(limit_products: int | None = None) -> pd.DataFrame:
    limit_clause = ""
    if limit_products:
        limit_clause = f"""
        WHERE product_id IN (
            SELECT product_id
            FROM `{raw_table_ref(RAW_CANDIDATES_TABLE)}`
            GROUP BY product_id
            ORDER BY MIN(review_count_rank)
            LIMIT {limit_products}
        )
        """
    query = f"""
        SELECT
            product_id,
            product_name,
            brand_name,
            review_count_rank,
            candidate_rank,
            search_keyword,
            source,
            hero_words,
            product_type
        FROM `{raw_table_ref(RAW_CANDIDATES_TABLE)}`
        {limit_clause}
        ORDER BY product_id, candidate_rank
    """
    return query_dataframe(query)


def _new_pytrends() -> TrendReq:
    return TrendReq(hl="en-US", tz=300)


def _is_rate_limit_error(exc: Exception) -> bool:
    return "429" in str(exc)


def _backoff_seconds(attempt: int, *, rate_limited: bool) -> float:
    base = DEFAULT_RATE_LIMIT_BASE_SECONDS if rate_limited else 2.0
    return base * (2 ** (attempt - 1)) + random.uniform(2.0, 8.0)


def probe_keywords(
    pytrends: TrendReq,
    keywords: list[str],
    *,
    anchor: str | None,
    timeframe: str,
    geo: str,
    max_retries: int,
) -> tuple[pd.DataFrame, TrendReq]:
    kw_list = [anchor, *keywords] if anchor else list(keywords)
    for attempt in range(1, max_retries + 1):
        try:
            pytrends.build_payload(kw_list, cat=0, timeframe=timeframe, geo=geo, gprop="")
            df = pytrends.interest_over_time()
            if df.empty:
                return pd.DataFrame(), pytrends

            if "isPartial" in df.columns:
                df = df.drop(columns=["isPartial"])

            melted = pd.melt(
                df.reset_index(),
                id_vars=["date"],
                value_vars=kw_list,
                var_name="search_keyword",
                value_name="search_interest",
            )
            if anchor:
                return melted[melted["search_keyword"] != anchor], pytrends
            return melted, pytrends
        except Exception as exc:
            rate_limited = _is_rate_limit_error(exc)
            wait_seconds = _backoff_seconds(attempt, rate_limited=rate_limited)
            print(f"  Error probing {keywords} (attempt {attempt}/{max_retries}): {exc}")
            if attempt < max_retries:
                if rate_limited:
                    print(f"  Rate limited — waiting {wait_seconds:.0f}s...")
                    time.sleep(wait_seconds)
                    pytrends = _new_pytrends()
                else:
                    time.sleep(wait_seconds)
            else:
                raise

    return pd.DataFrame(), pytrends


def score_probe_results(probe_df: pd.DataFrame, keywords: list[str]) -> pd.DataFrame:
    if probe_df.empty:
        return pd.DataFrame(
            {
                "search_keyword": keywords,
                "probe_avg_interest": 0.0,
                "probe_max_interest": 0.0,
                "probe_nonzero_weeks": 0,
                "probe_total_weeks": 0,
            }
        )

    summary = (
        probe_df.groupby("search_keyword", as_index=False)
        .agg(
            probe_avg_interest=("search_interest", "mean"),
            probe_max_interest=("search_interest", "max"),
            probe_nonzero_weeks=("search_interest", lambda s: int((s > 0).sum())),
            probe_total_weeks=("search_interest", "count"),
        )
        .astype({"probe_nonzero_weeks": int, "probe_total_weeks": int})
    )

    missing = set(keywords) - set(summary["search_keyword"])
    if missing:
        summary = pd.concat(
            [
                summary,
                pd.DataFrame(
                    {
                        "search_keyword": list(missing),
                        "probe_avg_interest": 0.0,
                        "probe_max_interest": 0.0,
                        "probe_nonzero_weeks": 0,
                        "probe_total_weeks": 0,
                    }
                ),
            ],
            ignore_index=True,
        )
    return summary


def pick_winner(
    product_row: pd.Series,
    candidates: pd.DataFrame,
    scores: pd.DataFrame,
) -> dict:
    merged = candidates.merge(scores, on="search_keyword", how="left")
    merged = merged.sort_values(
        by=[
            "probe_avg_interest",
            "probe_nonzero_weeks",
            "probe_max_interest",
            "candidate_rank",
        ],
        ascending=[False, False, False, True],
    )
    winner = merged.iloc[0]
    return {
        "product_id": product_row["product_id"],
        "product_name": product_row["product_name"],
        "brand_name": product_row["brand_name"],
        "review_count_rank": int(product_row["review_count_rank"]),
        "search_keyword": winner["search_keyword"],
        "hero_words": winner.get("hero_words"),
        "product_type": winner.get("product_type"),
        "candidate_rank": int(winner["candidate_rank"]),
        "candidate_source": winner.get("source"),
        "probe_avg_interest": float(winner["probe_avg_interest"]),
        "probe_max_interest": float(winner["probe_max_interest"]),
        "probe_nonzero_weeks": int(winner["probe_nonzero_weeks"]),
        "probe_total_weeks": int(winner["probe_total_weeks"]),
        "probed_at": datetime.now(timezone.utc).isoformat(),
    }


def select_rank1_winners(candidates: pd.DataFrame) -> pd.DataFrame:
    """Promote each product's top candidate (candidate_rank 1) without probing.

    Used by --no-fetch: trusts the generation ordering instead of an empirical
    Google Trends bake-off. Probe metrics are left null (no probe was run).
    """
    winners: list[dict] = []
    for product_id in candidates["product_id"].drop_duplicates():
        product_candidates = candidates[candidates["product_id"] == product_id]
        winner = product_candidates.sort_values("candidate_rank").iloc[0]
        winners.append(
            {
                "product_id": winner["product_id"],
                "product_name": winner["product_name"],
                "brand_name": winner["brand_name"],
                "review_count_rank": int(winner["review_count_rank"]),
                "search_keyword": winner["search_keyword"],
                "hero_words": winner.get("hero_words"),
                "product_type": winner.get("product_type"),
                "candidate_rank": int(winner["candidate_rank"]),
                "candidate_source": winner.get("source"),
                "probe_avg_interest": None,
                "probe_max_interest": None,
                "probe_nonzero_weeks": None,
                "probe_total_weeks": None,
                "probed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return pd.DataFrame(winners)


def run(
    *,
    limit_products: int | None,
    anchor: str | None,
    sleep_seconds: float,
    max_retries: int,
    timeframe: str,
    geo: str,
    dry_run: bool,
    no_fetch: bool = False,
) -> None:
    candidates = fetch_candidates(limit_products=limit_products)
    if candidates.empty:
        raise SystemExit(
            f"No rows in raw.{RAW_CANDIDATES_TABLE}. Run generate_product_search_keywords.py first."
        )

    if no_fetch:
        winners_df = select_rank1_winners(candidates)
        print(
            f"Selected candidate_rank 1 for {len(winners_df)} products "
            f"(no probing — trusting generation order)."
        )
        if dry_run:
            print(winners_df.head(12).to_string(index=False))
            return
        load_dataframe(
            winners_df,
            dataset="raw",
            table=RAW_KEYWORDS_TABLE,
            replace=True,
        )
        return

    pytrends = _new_pytrends()
    winners: list[dict] = []
    product_ids = candidates["product_id"].drop_duplicates().tolist()
    print(f"Probing keyword candidates for {len(product_ids)} products...")

    for index, product_id in enumerate(product_ids, start=1):
        product_candidates = candidates[candidates["product_id"] == product_id].copy()
        product_row = product_candidates.iloc[0]
        keywords = product_candidates["search_keyword"].tolist()[:3]
        print(
            f"[{index}/{len(product_ids)}] {product_row['brand_name']} — "
            f"{product_row['product_name'][:60]} -> {keywords}"
        )

        try:
            probe_df, pytrends = probe_keywords(
                pytrends,
                keywords,
                anchor=anchor,
                timeframe=timeframe,
                geo=geo,
                max_retries=max_retries,
            )
        except Exception as exc:
            print(f"  Skipping product after probe failures: {exc}")
            pytrends = _new_pytrends()
            probe_df = pd.DataFrame()

        scores = score_probe_results(probe_df, keywords)
        winners.append(pick_winner(product_row, product_candidates, scores))

        if sleep_seconds:
            time.sleep(sleep_seconds)

    winners_df = pd.DataFrame(winners)
    signal_count = int((winners_df["probe_avg_interest"] > 0).sum())
    print(
        f"Picked keywords for {len(winners_df)} products "
        f"({signal_count} with non-zero probe signal)."
    )

    if dry_run:
        print(winners_df.head(12).to_string(index=False))
        return

    load_dataframe(
        winners_df,
        dataset="raw",
        table=RAW_KEYWORDS_TABLE,
        replace=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit-products",
        type=int,
        default=None,
        help="Probe only the first N pilot products by review rank",
    )
    parser.add_argument(
        "--anchor",
        default=DEFAULT_ANCHOR,
        help=f"Anchor keyword used during probing (default: {DEFAULT_ANCHOR})",
    )
    parser.add_argument(
        "--no-anchor",
        action="store_true",
        help=(
            "Anchorless mode: probe each product's candidates against each other "
            "(no shared anchor). Picks the strongest phrasing without anchor flooring."
        ),
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=DEFAULT_SLEEP_SECONDS,
        help="Seconds to wait between product probes",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Retries per probe when Google rate-limits (429)",
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
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help=(
            "Skip Google Trends entirely and promote each product's candidate_rank 1 "
            "as the winner (trusts generation ordering; no empirical probe)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print winners without loading to BigQuery",
    )
    args = parser.parse_args()

    run(
        limit_products=args.limit_products,
        anchor=None if args.no_anchor else args.anchor,
        sleep_seconds=args.sleep,
        max_retries=args.max_retries,
        timeframe=args.timeframe,
        geo=args.geo,
        dry_run=args.dry_run,
        no_fetch=args.no_fetch,
    )


if __name__ == "__main__":
    main()
