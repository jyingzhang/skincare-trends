"""Generate Google Trends keyword candidates for pilot products (rules + LLM)."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from bigquery_io import load_dataframe, model_table_ref, query_dataframe
from product_search_keywords_lib import (
    build_llm_prompt,
    enforce_keyword_rules,
    extract_product_type,
    merge_candidates,
    normalize_brand,
    parse_llm_response,
    rule_based_candidates,
)

load_dotenv()

RAW_CANDIDATES_TABLE = "raw_product_search_keyword_candidates"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_BATCH_SIZE = 40


def fetch_pilot_products(limit: int | None = None) -> pd.DataFrame:
    limit_clause = f"LIMIT {limit}" if limit else ""
    query = f"""
        SELECT
            product_id,
            product_name,
            brand_name,
            review_count_rank
        FROM `{model_table_ref('int_pilot_product_cohort')}`
        ORDER BY review_count_rank
        {limit_clause}
    """
    return query_dataframe(query)


def call_llm_batch(
    client: OpenAI,
    products: list[dict[str, str]],
    *,
    model: str,
) -> list[dict]:
    prompt = build_llm_prompt(products)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You write concise Google search keyword candidates for skincare products. "
                    "Return valid JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    return parse_llm_response(response.choices[0].message.content)


def build_candidate_rows(
    products: pd.DataFrame,
    llm_by_product: dict[str, dict],
) -> pd.DataFrame:
    generated_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []

    for row in products.itertuples(index=False):
        llm_payload = llm_by_product.get(row.product_id, {})
        llm_candidates = llm_payload.get("candidates", [])
        if isinstance(llm_candidates, str):
            llm_candidates = [llm_candidates]

        hero_words = llm_payload.get("hero_words", [])
        if isinstance(hero_words, str):
            hero_words = [hero_words]

        product_type = llm_payload.get("product_type") or extract_product_type(
            row.product_name
        )
        merged = merge_candidates(
            llm_candidates=[str(item) for item in llm_candidates],
            rule_candidates=rule_based_candidates(row.brand_name, row.product_name),
            max_candidates=3,
        )

        brand_norm = normalize_brand(row.brand_name)
        enforced: list[tuple[str, str]] = []
        seen_enforced: set[str] = set()
        for keyword, source in merged:
            fixed = enforce_keyword_rules(
                keyword,
                product_name=row.product_name,
                product_type=product_type,
                brand_norm=brand_norm,
            )
            if fixed and fixed not in seen_enforced:
                enforced.append((fixed, source))
                seen_enforced.add(fixed)
        merged = enforced

        for rank, (keyword, source) in enumerate(merged, start=1):
            rows.append(
                {
                    "product_id": row.product_id,
                    "product_name": row.product_name,
                    "brand_name": row.brand_name,
                    "review_count_rank": row.review_count_rank,
                    "candidate_rank": rank,
                    "search_keyword": keyword,
                    "source": source,
                    "hero_words": ", ".join(str(word) for word in hero_words),
                    "product_type": product_type,
                    "generated_at": generated_at,
                }
            )

    return pd.DataFrame(rows)


def generate_with_llm(
    products: pd.DataFrame,
    *,
    model: str,
    batch_size: int,
) -> dict[str, dict]:
    if products.empty:
        return {}

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required unless --rules-only is set.")

    client = OpenAI(api_key=api_key)
    llm_by_product: dict[str, dict] = {}
    records = products[["product_id", "brand_name", "product_name"]].to_dict("records")

    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        batch_num = start // batch_size + 1
        total_batches = (len(records) + batch_size - 1) // batch_size
        print(f"LLM batch {batch_num}/{total_batches} ({len(batch)} products)...")
        parsed = call_llm_batch(client, batch, model=model)
        for item in parsed:
            llm_by_product[str(item["product_id"])] = item

    return llm_by_product


def run(
    *,
    limit: int | None,
    model: str,
    batch_size: int,
    rules_only: bool,
    dry_run: bool,
) -> None:
    products = fetch_pilot_products(limit=limit)
    if products.empty:
        raise SystemExit(
            "No rows in int_pilot_product_cohort. Run: "
            "dbt run --select int_pilot_product_cohort"
        )

    print(f"Generating keyword candidates for {len(products)} pilot products...")
    llm_by_product = {} if rules_only else generate_with_llm(
        products,
        model=model,
        batch_size=batch_size,
    )
    candidates_df = build_candidate_rows(products, llm_by_product)

    if candidates_df.empty:
        raise SystemExit("No keyword candidates generated.")

    print(
        f"Built {len(candidates_df):,} candidates "
        f"for {candidates_df['product_id'].nunique()} products."
    )
    print(candidates_df["source"].value_counts().to_string())

    if dry_run:
        print(candidates_df.head(12).to_string(index=False))
        return

    load_dataframe(
        candidates_df,
        dataset="raw",
        table=RAW_CANDIDATES_TABLE,
        replace=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Generate candidates for the first N pilot products only",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI model (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Products per LLM request",
    )
    parser.add_argument(
        "--rules-only",
        action="store_true",
        help="Skip LLM and use rule-based candidates only",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print sample output without loading to BigQuery",
    )
    args = parser.parse_args()

    run(
        limit=args.limit,
        model=args.model,
        batch_size=args.batch_size,
        rules_only=args.rules_only,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
