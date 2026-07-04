"""Benchmark ingredient Google Trends anchor candidates.

This reproduces the evidence used to choose an ingredient anchor term by
testing candidate anchors across top ingredient chunks.
"""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import pandas as pd
from pytrends.request import TrendReq

DEFAULT_CANDIDATES = [
    "retinol",
    "niacinamide",
    "hyaluronic acid",
    "salicylic acid",
    "glycolic acid",
    "vitamin c",
]


def parse_args() -> argparse.Namespace:
    # Keep benchmark controls configurable for reproducibility.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed-csv",
        default="dbt_project/seeds/top_used_ingredients_benefits.csv",
        help="Path to ingredient seed CSV, relative to project root",
    )
    parser.add_argument(
        "--output-dir",
        default="analysis",
        help="Output directory, relative to project root",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Top N ingredients by product_count to include",
    )
    parser.add_argument(
        "--probe-size",
        type=int,
        default=20,
        help="Probe set size for benchmark runtime",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=4,
        help="Keywords per Google request excluding anchor (max 4)",
    )
    parser.add_argument(
        "--timeframe",
        default="today 12-m",
        help="Google Trends timeframe",
    )
    parser.add_argument("--geo", default="US", help="Google Trends geo")
    parser.add_argument("--sleep", type=float, default=3.0, help="Sleep between chunks")
    parser.add_argument("--max-retries", type=int, default=5, help="Retries per chunk")
    parser.add_argument(
        "--candidates",
        default=",".join(DEFAULT_CANDIDATES),
        help="Comma-separated anchor candidates",
    )
    return parser.parse_args()


def benchmark_anchor(
    pytrends: TrendReq,
    anchor: str,
    chunks: list[list[str]],
    timeframe: str,
    geo: str,
    sleep_seconds: float,
    max_retries: int,
) -> list[dict]:
    rows: list[dict] = []
    for chunk_idx, chunk in enumerate(chunks, 1):
        # Google accepts up to 5 terms/request; one slot is reserved for anchor.
        kw_list = [anchor] + chunk
        success = False
        for attempt in range(1, max_retries + 1):
            try:
                pytrends.build_payload(kw_list, cat=0, timeframe=timeframe, geo=geo, gprop="")
                df = pytrends.interest_over_time()
                if df.empty:
                    break
                if "isPartial" in df.columns:
                    df = df.drop(columns=["isPartial"])
                s = df[anchor].astype(float)
                # Anchor quality metrics:
                # - zero/low shares for sparse baseline risk
                # - cv for volatility
                # - high_share_ge_90 for saturation risk
                rows.append(
                    {
                        "anchor": anchor,
                        "chunk": chunk_idx,
                        "mean": float(s.mean()),
                        "median": float(s.median()),
                        "cv": float(s.std(ddof=0) / s.mean()) if s.mean() else math.nan,
                        "zero_share": float((s == 0).mean()),
                        "low_share_le_5": float((s <= 5).mean()),
                        "high_share_ge_90": float((s >= 90).mean()),
                    }
                )
                success = True
                break
            except Exception as exc:
                # Retry with backoff on transient Google rate limits.
                if "429" in str(exc) and attempt < max_retries:
                    wait = sleep_seconds * attempt * 2
                    print(f"[{anchor}] chunk {chunk_idx}: 429; waiting {wait:.0f}s")
                    time.sleep(wait)
                    continue
                print(f"[{anchor}] chunk {chunk_idx}: failed: {exc}")
                break

        if not success:
            rows.append(
                {
                    "anchor": anchor,
                    "chunk": chunk_idx,
                    "mean": math.nan,
                    "median": math.nan,
                    "cv": math.nan,
                    "zero_share": math.nan,
                    "low_share_le_5": math.nan,
                    "high_share_ge_90": math.nan,
                }
            )
        time.sleep(sleep_seconds)
    return rows


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    # Aggregate per-anchor metrics over all chunks.
    summary = (
        df.groupby("anchor", as_index=False)
        .agg(
            chunks=("chunk", "count"),
            successful_chunks=("mean", lambda s: int(s.notna().sum())),
            avg_mean=("mean", "mean"),
            avg_median=("median", "mean"),
            avg_cv=("cv", "mean"),
            avg_zero_share=("zero_share", "mean"),
            avg_low_share_le_5=("low_share_le_5", "mean"),
            avg_high_share_ge_90=("high_share_ge_90", "mean"),
        )
    )
    # Composite score (lower is better):
    # favor anchors with low sparsity + low volatility and usable scale.
    summary["score"] = (
        0.35 * summary["avg_zero_share"].fillna(1)
        + 0.20 * summary["avg_low_share_le_5"].fillna(1)
        + 0.20 * summary["avg_cv"].fillna(10)
        + 0.10 * summary["avg_high_share_ge_90"].fillna(1)
        + 0.15 * ((summary["avg_mean"] - 35).abs() / 35).fillna(2)
    )
    return summary.sort_values("score")


def main() -> None:
    args = parse_args()
    if args.chunk_size > 4:
        raise SystemExit("chunk-size must be <= 4")
    if args.limit <= 0:
        raise SystemExit("limit must be > 0")
    if args.probe_size <= 0:
        raise SystemExit("probe-size must be > 0")

    project_root = Path(__file__).resolve().parents[1]
    seed_path = (project_root / args.seed_csv).resolve()
    out_dir = (project_root / args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates = [item.strip().lower() for item in args.candidates.split(",") if item.strip()]

    # Match ingest behavior: rank by product_count, then cap by --limit.
    seed = pd.read_csv(seed_path)
    seed = seed.dropna(subset=["ingredient_name"])
    seed["ingredient_name"] = seed["ingredient_name"].astype(str).str.strip().str.lower()

    probe_keywords = (
        seed.sort_values("product_count", ascending=False)["ingredient_name"]
        .drop_duplicates()
        .head(args.limit)
        .head(args.probe_size)
        .tolist()
    )

    # Reuse one pytrends client/session for all anchor candidates.
    pytrends = TrendReq(hl="en-US", tz=300)
    rows: list[dict] = []
    for anchor in candidates:
        kws = [name for name in probe_keywords if name != anchor]
        chunks = [kws[i : i + args.chunk_size] for i in range(0, len(kws), args.chunk_size)]
        print(f"Benchmarking anchor: {anchor}")
        rows.extend(
            benchmark_anchor(
                pytrends,
                anchor,
                chunks,
                timeframe=args.timeframe,
                geo=args.geo,
                sleep_seconds=args.sleep,
                max_retries=args.max_retries,
            )
        )

    chunk_df = pd.DataFrame(rows)
    summary_df = summarize(chunk_df)

    # Persist detailed evidence and ranked summary for reporting.
    chunk_path = out_dir / "ingredient_anchor_benchmark_chunk_metrics.csv"
    summary_path = out_dir / "ingredient_anchor_benchmark_summary.csv"
    probe_path = out_dir / "ingredient_anchor_probe_keywords.txt"
    chunk_df.to_csv(chunk_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    probe_path.write_text("\n".join(probe_keywords))

    print("\n=== Ingredient Anchor Benchmark Summary ===")
    print(summary_df.to_string(index=False))
    print("\nSaved:")
    print(summary_path)
    print(chunk_path)
    print(probe_path)


if __name__ == "__main__":
    main()
