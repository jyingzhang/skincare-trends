"""Benchmark product Google Trends anchor candidates.

This reproduces the evidence used to choose a product anchor term by testing
candidate anchors across representative product keyword chunks.
"""

from __future__ import annotations

import argparse
import math
import random
import re
import time
from pathlib import Path

import pandas as pd
from pytrends.request import TrendReq

DEFAULT_CANDIDATES = [
    "face cleanser",
    "face wash",
    "moisturizer",
    "sunscreen",
    "face serum",
    "eye cream",
]


def parse_args() -> argparse.Namespace:
    # Keep knobs configurable so the benchmark can be rerun/reviewed later.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--product-csv",
        default="data/raw/sephora/product_info.csv",
        help="Path to product_info.csv, relative to project root",
    )
    parser.add_argument(
        "--output-dir",
        default="analysis",
        help="Output directory, relative to project root",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=16,
        help="Number of product keywords to probe",
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
        "--seed",
        type=int,
        default=42,
        help="Sampling seed",
    )
    parser.add_argument(
        "--candidates",
        default=",".join(DEFAULT_CANDIDATES),
        help="Comma-separated anchor candidates",
    )
    return parser.parse_args()


def make_search_keyword(brand: str, product: str) -> str:
    # Approximate int_pilot_products search_keyword construction so the benchmark
    # tests realistic terms sent to the Google Trends API.
    parens_pattern = re.compile(r"\([^)]*\)")
    stopwords_pattern = re.compile(
        r"\b(limited edition|jumbo|duo|travel size|refillable)\b", flags=re.IGNORECASE
    )
    suffix_pattern = re.compile(r"\s+(with|intense|refillable|and).*$", flags=re.IGNORECASE)

    name = parens_pattern.sub("", str(product))
    name = stopwords_pattern.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = suffix_pattern.sub("", name).strip()
    words = name.split()[:5]
    base = f"{str(brand).strip()} {' '.join(words)}".strip().lower()
    if "mini" in str(product).lower() and not base.endswith(" mini"):
        base += " mini"
    return re.sub(r"\s+", " ", base).strip()


def build_probe_keywords(product_csv: Path, sample_size: int, seed: int) -> list[str]:
    # Build a representative probe set from high-review skincare products:
    # - constrained to skincare,
    # - minimum review floor,
    # - de-duplicated by generated search keyword.
    pdf = pd.read_csv(product_csv)
    skin = pdf[pdf["primary_category"] == "Skincare"].copy()
    skin = skin[skin["reviews"].fillna(0) >= 500].copy()
    skin = skin.sort_values(["reviews", "product_id"], ascending=[False, True])
    skin["search_keyword"] = skin.apply(
        lambda row: make_search_keyword(row["brand_name"], row["product_name"]), axis=1
    )
    skin = skin.dropna(subset=["search_keyword"])
    skin = skin[skin["search_keyword"].str.len() > 0]
    skin = skin.drop_duplicates("search_keyword")

    if len(skin) <= sample_size:
        return skin["search_keyword"].tolist()

    # Split sample between top-ranked products and random remainder to avoid
    # overfitting to only blockbuster items.
    random.seed(seed)
    top = skin["search_keyword"].head(sample_size // 2).tolist()
    remainder = skin["search_keyword"].iloc[sample_size // 2 :].tolist()
    rand = random.sample(remainder, sample_size - len(top))
    return top + rand


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
        # Google accepts up to 5 terms/request; one slot is always the anchor.
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
                # - zero/low shares capture sparse baselines
                # - cv captures volatility
                # - high_share_ge_90 captures saturation risk
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
                # 429s are common with pytrends; backoff and retry.
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
    # Aggregate per-anchor metrics across all tested chunks.
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
    # - penalize sparse anchors and unstable anchors
    # - penalize anchors that saturate near 100 too often
    # - gently prefer anchors with a mid-range mean (~35)
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
    if args.sample_size <= 0:
        raise SystemExit("sample-size must be > 0")

    project_root = Path(__file__).resolve().parents[1]
    product_csv = (project_root / args.product_csv).resolve()
    out_dir = (project_root / args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates = [item.strip().lower() for item in args.candidates.split(",") if item.strip()]
    probe_keywords = build_probe_keywords(product_csv, args.sample_size, args.seed)
    chunks = [probe_keywords[i : i + args.chunk_size] for i in range(0, len(probe_keywords), args.chunk_size)]

    # Reuse one pytrends client/session for all anchors.
    pytrends = TrendReq(hl="en-US", tz=300)
    rows: list[dict] = []
    for anchor in candidates:
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

    # Persist both detailed chunk-level evidence and ranked summary.
    chunk_path = out_dir / "anchor_benchmark_chunk_metrics.csv"
    summary_path = out_dir / "anchor_benchmark_summary.csv"
    probe_path = out_dir / "anchor_benchmark_probe_keywords.txt"
    chunk_df.to_csv(chunk_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    probe_path.write_text("\n".join(probe_keywords))

    print("\n=== Product Anchor Benchmark Summary ===")
    print(summary_df.to_string(index=False))
    print("\nSaved:")
    print(summary_path)
    print(chunk_path)
    print(probe_path)


if __name__ == "__main__":
    main()
