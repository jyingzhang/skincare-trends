"""Summarize Sephora product reviews with OpenAI and load into DuckDB."""

from __future__ import annotations

import argparse
import os
import textwrap
import time
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from db import connect, ensure_raw_schema

load_dotenv()

MODEL = "gpt-4o-mini"
DEFAULT_SAMPLE_SIZE = 40 # number of reviews to sample per product for AI summary    
MAX_REVIEW_CHARS = 400 # maximum number of characters for a review to be included in the AI summary
SUMMARY_TABLE = "raw.raw_product_review_summaries" 


def get_products(con, max_products: int | None) -> pd.DataFrame:
    # get the products with the most reviews
    limit_clause = f"LIMIT {max_products}" if max_products else ""
    query = f"""
        SELECT
            r.product_id,
            MAX(r.product_name) AS product_name,
            MAX(r.brand_name) AS brand_name,
            COUNT(*) AS total_review_count,
            ROUND(AVG(r.rating), 2) AS avg_rating
        FROM raw.raw_sephora_reviews AS r
        INNER JOIN raw.raw_sephora_products AS p
            ON r.product_id = p.product_id
        WHERE p.primary_category = 'Skincare'
            AND r.review_text IS NOT NULL
            AND TRIM(r.review_text) != ''
        GROUP BY r.product_id
        ORDER BY total_review_count DESC
        {limit_clause}
    """
    return con.execute(query).fetch_df()


def get_existing_product_ids(con) -> set[str]:
    # get the existing product ids from the summary table
    tables = con.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = 'raw'
            AND table_name = 'raw_product_review_summaries'
        """
    ).fetchone()[0]
    if tables == 0:
        return set()
    ids = con.execute(f"SELECT product_id FROM {SUMMARY_TABLE}").fetchall()
    return {row[0] for row in ids}


def sample_reviews(con, product_id: str, sample_size: int) -> pd.DataFrame:
    # sample reviews for the product
    query = """
        SELECT rating, review_title, review_text
        FROM raw.raw_sephora_reviews
        WHERE product_id = ?
            AND review_text IS NOT NULL
            AND TRIM(review_text) != ''
        ORDER BY random()
        LIMIT ?
    """
    return con.execute(query, [product_id, sample_size]).fetch_df()


def _clean_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def format_reviews_for_prompt(reviews: pd.DataFrame) -> str:
    # format the reviews for the prompt
    blocks = []
    for row in reviews.itertuples(index=False):
        title = _clean_text(row.review_title)
        text = _clean_text(row.review_text)
        if len(text) > MAX_REVIEW_CHARS:
            text = text[:MAX_REVIEW_CHARS].rstrip() + "..."
        header = f"[rating {row.rating}]"
        if title:
            header += f" {title}"
        blocks.append(f"{header}\n{text}")
    return "\n\n---\n\n".join(blocks)


def summarize_reviews(
    client: OpenAI,
    product_name: str,
    brand_name: str,
    review_blob: str,
) -> str:
    prompt = textwrap.dedent(
        f"""
        You are analyzing customer reviews for a Sephora skincare product.

        Product: {product_name}
        Brand: {brand_name}

        Below is a random sample of customer reviews (with star ratings).

        Write 1-2 sentences summarizing what customers usually praise and what they
        commonly complain about. Be specific and grounded in the reviews.
        Do not invent claims that are not supported by the sample.
        Do not mention that this is a sample.

        Reviews:
        {review_blob}
        """
    ).strip()

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You write concise, factual product review summaries for analysts."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=150,
    )
    return response.choices[0].message.content.strip()


def ensure_summary_table(con, full_refresh: bool) -> None:
    # ensure the summary table exists
    ensure_raw_schema(con)
    if full_refresh:
        con.execute(f"DROP TABLE IF EXISTS {SUMMARY_TABLE}")

    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {SUMMARY_TABLE} (
            product_id VARCHAR,
            product_name VARCHAR,
            brand_name VARCHAR,
            total_review_count BIGINT,
            avg_rating DOUBLE,
            review_sample_size BIGINT,
            summary VARCHAR,
            model_name VARCHAR,
            summarized_at TIMESTAMP
        )
        """
    )


def insert_summary(con, row: dict) -> None:
    # insert the summary into the summary table
    con.execute(
        f"""
        INSERT INTO {SUMMARY_TABLE} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            row["product_id"],
            row["product_name"],
            row["brand_name"],
            row["total_review_count"],
            row["avg_rating"],
            row["review_sample_size"],
            row["summary"],
            row["model_name"],
            row["summarized_at"],
        ],
    )


def run(
    max_products: int | None,
    sample_size: int,
    full_refresh: bool,
    product_id: str | None,
    sleep_seconds: float,
) -> None:

    # run the summary

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("Error: Missing OPENAI_API_KEY environment variable.")
        
    # create the OpenAI client
    client = OpenAI(api_key=api_key)
    # connect to the database
    con = connect()
    # ensure the summary table exists
    ensure_summary_table(con, full_refresh=full_refresh)

    existing_ids = set() if full_refresh else get_existing_product_ids(con)


    # get the products to process
    if product_id:
        products = get_products(con, max_products=None)
        products = products[products["product_id"] == product_id]
        if products.empty:
            raise SystemExit(f"Error: No skincare reviews found for product_id={product_id}")
        existing_ids -= {product_id}
    else:
        products = get_products(con, max_products=max_products)
    
    # get number of products to process that havent been summarized yet
    to_process = products[~products["product_id"].isin(existing_ids)]
    total = len(to_process)
    print(f"Products to summarize: {total} (sample_size={sample_size}, model={MODEL})")

    # if no products to process, exit
    if total == 0:
        print("Nothing to do — all products already summarized. Use --full-refresh to rerun.")
        con.close()
        return

    success = 0

    # summarize the products
    for idx, product in enumerate(to_process.itertuples(index=False), start=1):
        print(f"[{idx}/{total}] {product.product_name} ({product.product_id})")

        reviews = sample_reviews(con, product.product_id, sample_size)
        if reviews.empty:
            print("  Skipping — no usable review text.")
            continue

        # format the reviews for the prompt
        review_blob = format_reviews_for_prompt(reviews)

        # summarize the reviews
        try:
            summary = summarize_reviews(
                client,
                product.product_name,
                product.brand_name,
                review_blob,
            )
        except Exception as exc:
            print(f"  OpenAI error: {exc}")
            continue

        # insert the summary into the summary table
        insert_summary(
            con,
            {
                "product_id": product.product_id,
                "product_name": product.product_name,
                "brand_name": product.brand_name,
                "total_review_count": int(product.total_review_count),
                "avg_rating": float(product.avg_rating),
                "review_sample_size": len(reviews),
                "summary": summary,
                "model_name": MODEL,
                "summarized_at": datetime.now(timezone.utc),
            },
        )
        success += 1 # increment the success counter
        print(f"  {summary}")

        if sleep_seconds:
            time.sleep(sleep_seconds)

    count = con.execute(f"SELECT COUNT(*) FROM {SUMMARY_TABLE}").fetchone()[0]
    print(f"Done. {success} new summaries written. {count} total rows in {SUMMARY_TABLE}.")
    con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-products",
        type=int,
        default=None,
        help="Limit number of products to process (default: all skincare products)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help=f"Random reviews sampled per product (default: {DEFAULT_SAMPLE_SIZE})",
    )
    parser.add_argument(
        "--product-id",
        type=str,
        default=None,
        help="Summarize a single product by ID (e.g. P420652)",
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Drop and rebuild the summary table",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.5,
        help="Seconds to wait between API calls (default: 0.5)",
    )
    args = parser.parse_args()

    run(
        max_products=args.max_products,
        sample_size=args.sample_size,
        full_refresh=args.full_refresh,
        product_id=args.product_id,
        sleep_seconds=args.sleep,
    )


if __name__ == "__main__":
    main()
