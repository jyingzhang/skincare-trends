"""Shared helpers for Google Trends product search keyword generation."""

from __future__ import annotations

import json
import re
import textwrap
import unicodedata
from typing import Any

PRODUCT_TYPE_PATTERNS: list[tuple[str, str]] = [
    (r"\blip sleeping mask\b", "lip mask"),
    (r"\bsleeping mask\b", "sleeping mask"),
    (r"\blip mask\b", "lip mask"),
    (r"\beye serum\b", "eye serum"),
    (r"\beye cream\b", "eye cream"),
    (r"\bface wash\b", "face wash"),
    (r"\bface cleanser\b", "cleanser"),
    (r"\bcleansing balm\b", "cleansing balm"),
    (r"\bcleansing oil\b", "cleansing oil"),
    (r"\bmakeup removing\b.*\bbalm\b", "cleansing balm"),
    (r"\btoner\b", "toner"),
    (r"\bprimer\b", "primer"),
    (r"\bdew drops\b", "serum"),
    (r"\bessence\b", "essence"),
    (r"\bmist\b", "mist"),
    (r"\bsunscreen\b", "sunscreen"),
    (r"\bspf\b", "sunscreen"),
    (r"\bserum\b", "serum"),
    (r"\bmoisturizer\b", "moisturizer"),
    (r"\bmoisturiser\b", "moisturizer"),
    (r"\bcream\b", "moisturizer"),
    (r"\blotion\b", "moisturizer"),
    (r"\bpeel(?:ing)? solution\b", "peel"),
    (r"\bpeel pads\b", "peel"),
    (r"\bpeel\b", "peel"),
    (r"\bargan oil\b", "argan oil"),
    (r"\bface oil\b", "face oil"),
    (r"\boil\b", "oil"),
    (r"\bmask\b", "mask"),
    (r"\bbalm\b", "balm"),
    (r"\bcleanser\b", "cleanser"),
]

STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "with",
    "the",
    "percent",
    "pure",
    "daily",
    "extra",
    "strength",
    "intense",
    "hydration",
    "hydrating",
    "gentle",
    "brightening",
    "dark",
    "spot",
    "removing",
    "makeup",
    "meltaway",
    "limited",
    "edition",
    "jumbo",
    "duo",
    "travel",
    "size",
    "refillable",
    "mini",
    "skincare",
    "face",
    "facial",
    "formula",
    "treatment",
    "solution",
    "concentrate",
    "complex",
    "advanced",
    "repair",
    "cream",
    "lotion",
    "serum",
    "cleanser",
    "toner",
    "moisturizer",
    "sunscreen",
    "mask",
    "balm",
    "oil",
    "peel",
    "mist",
    "essence",
    "wash",
    "cleansing",
    "sleeping",
    "lip",
    "eye",
}

MARKETING_SUFFIX_PATTERN = re.compile(
    r"\s+(with|intense|refillable|and).*$",
    flags=re.IGNORECASE,
)
PARENS_PATTERN = re.compile(r"\([^)]*\)")
MARKETING_PATTERN = re.compile(
    r"\b(limited edition|jumbo|duo|travel size|refillable)\b",
    flags=re.IGNORECASE,
)
# Strip apostrophes so possessives collapse (e.g. "kiehl's" -> "kiehls")
# instead of splitting into two tokens ("kiehl s") when non-alnum chars
# are later replaced with spaces.
APOSTROPHE_PATTERN = re.compile(r"[\u0027\u2018\u2019]")
PERCENT_PATTERN = re.compile(r"\b\d+\s*(?:%|percent)\b", flags=re.IGNORECASE)
NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9\s\+]")
MULTISPACE_PATTERN = re.compile(r"\s+")

FEW_SHOT_EXAMPLES = [
    {
        "brand_name": "Tatcha",
        "product_name": "Luminous Dewy Skin Mist",
        "hero_words": ["dewy"],
        "product_type": "mist",
        "candidates": [
            "tatcha skin mist",
            "tatcha dewy mist",
            "tatcha mist",
        ],
    },
    {
        "brand_name": "Tatcha",
        "product_name": "Liquid Silk Canvas Featherweight Protective Primer",
        "hero_words": ["silk"],
        "product_type": "primer",
        "candidates": [
            "tatcha silk primer",
            "tatcha primer",
        ],
    },
    {
        "brand_name": "Tatcha",
        "product_name": "The Rice Wash Skin-Softening Cleanser",
        "hero_words": ["rice"],
        "product_type": "cleanser",
        "candidates": [
            "tatcha rice cleanser",
            "tatcha cleanser",
        ],
    },
    {
        "brand_name": "Glow Recipe",
        "product_name": "Watermelon Glow PHA + BHA Pore-Tight Toner",
        "hero_words": ["watermelon"],
        "product_type": "toner",
        "candidates": [
            "glow recipe watermelon toner",
            "glow recipe toner",
            "glow recipe pha bha toner",
        ],
    },
    {
        "brand_name": "Glow Recipe",
        "product_name": "Watermelon Glow Niacinamide Dew Drops",
        "hero_words": ["dew drops", "watermelon"],
        "product_type": "serum",
        "candidates": [
            "glow recipe dew drops",
            "glow recipe watermelon dew drops",
            "glow recipe niacinamide dew drops",
        ],
    },
    {
        "brand_name": "LANEIGE",
        "product_name": "Lip Sleeping Mask Intense Hydration with Vitamin C",
        "hero_words": ["lip"],
        "product_type": "lip mask",
        "candidates": [
            "laneige lip mask",
            "laneige lip sleeping mask",
        ],
    },
    {
        "brand_name": "Biossance",
        "product_name": "Squalane + Omega Repair Deep Hydration Moisturizer",
        "hero_words": ["squalane", "omega"],
        "product_type": "moisturizer",
        "candidates": [
            "biossance squalane moisturizer",
            "biossance omega moisturizer",
        ],
    },
    {
        "brand_name": "Josie Maran",
        "product_name": "100 percent Pure Argan Oil",
        "hero_words": ["argan"],
        "product_type": "oil",
        "candidates": [
            "josie maran argan oil",
            "josie maran argan",
            "josie maran face oil",
        ],
    },
    {
        "brand_name": "Caudalie",
        "product_name": "Vinoperfect Brightening Dark Spot Serum",
        "hero_words": ["vinoperfect"],
        "product_type": "serum",
        "candidates": [
            "caudalie vinoperfect serum",
            "caudalie vinoperfect",
            "caudalie dark spot serum",
        ],
    },
    {
        "brand_name": "innisfree",
        "product_name": "Daily UV Defense Sunscreen SPF 36",
        "hero_words": ["daily uv"],
        "product_type": "sunscreen",
        "candidates": [
            "innisfree sunscreen",
            "innisfree daily uv sunscreen",
            "innisfree daily uv",
        ],
    },
]


def strip_accents(text: str) -> str:
    """Transliterate accented characters to ASCII (crème -> creme, lancôme -> lancome)."""
    decomposed = unicodedata.normalize("NFKD", str(text))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_brand(brand: str) -> str:
    return MULTISPACE_PATTERN.sub(" ", strip_accents(str(brand)).strip().lower())


def clean_product_name(product_name: str) -> str:
    name = PARENS_PATTERN.sub("", strip_accents(product_name))
    name = MARKETING_PATTERN.sub("", name)
    name = PERCENT_PATTERN.sub("", name)
    name = MARKETING_SUFFIX_PATTERN.sub("", name)
    name = APOSTROPHE_PATTERN.sub("", name.lower())
    name = NON_ALNUM_PATTERN.sub(" ", name)
    return MULTISPACE_PATTERN.sub(" ", name).strip()


def extract_product_type(product_name: str) -> str | None:
    cleaned = clean_product_name(product_name)
    for pattern, label in PRODUCT_TYPE_PATTERNS:
        if re.search(pattern, cleaned, flags=re.IGNORECASE):
            return label
    return None


def extract_rule_hero_words(product_name: str, product_type: str | None) -> list[str]:
    cleaned = clean_product_name(product_name)
    type_tokens = set((product_type or "").split())
    tokens = [
        token
        for token in cleaned.split()
        if token not in STOPWORDS and token not in type_tokens and not token.isdigit()
    ]
    if not tokens:
        return []

    heroes: list[str] = []
    if len(tokens) >= 2 and tokens[0] in {"green", "beauty", "daily", "super"}:
        heroes.append(" ".join(tokens[:2]))
        tokens = tokens[2:]
    if tokens:
        heroes.append(tokens[0])
    if len(tokens) > 1 and tokens[1] not in STOPWORDS:
        heroes.append(tokens[1])
    return heroes[:2]


def normalize_keyword(keyword: str) -> str:
    cleaned = APOSTROPHE_PATTERN.sub("", strip_accents(keyword).lower())
    cleaned = NON_ALNUM_PATTERN.sub(" ", cleaned)
    return MULTISPACE_PATTERN.sub(" ", cleaned).strip()


def enforce_keyword_rules(
    keyword: str,
    *,
    product_name: str,
    product_type: str | None,
    brand_norm: str,
) -> str:
    """Guarantee the mini + product-type-noun rules regardless of LLM output.

    - If the product is a "mini", ensure "mini" appears right after the brand.
    - If a product_type is known, ensure its core noun (last token) is present.
    """
    kw = normalize_keyword(keyword)
    if not kw:
        return kw
    tokens = kw.split()
    name_tokens = clean_product_name(product_name).split()
    # Match brand tokens using the SAME normalization as the keyword so brands
    # with punctuation (e.g. "Dr. Jart+") align with the keyword's tokens.
    brand_tokens = normalize_keyword(brand_norm).split()

    if "mini" in name_tokens and "mini" not in tokens:
        if brand_tokens and tokens[: len(brand_tokens)] == brand_tokens:
            tokens = brand_tokens + ["mini"] + tokens[len(brand_tokens) :]
        else:
            tokens = ["mini"] + tokens

    if product_type:
        core = normalize_keyword(product_type).split()
        core_noun = core[-1] if core else ""
        if core_noun and core_noun not in tokens:
            tokens.append(core_noun)

    return normalize_keyword(" ".join(tokens))


def legacy_search_keyword(brand: str, product_name: str) -> str:
    """Previous int_pilot_products keyword logic (fallback)."""
    name = PARENS_PATTERN.sub("", str(product_name))
    name = MARKETING_PATTERN.sub("", name)
    name = MULTISPACE_PATTERN.sub(" ", name).strip()
    name = MARKETING_SUFFIX_PATTERN.sub("", name).strip()
    words = name.split()[:5]
    keyword = f"{normalize_brand(brand)} {' '.join(words).lower()}".strip()
    if "mini" in str(product_name).lower() and not keyword.endswith(" mini"):
        keyword += " mini"
    return normalize_keyword(keyword)


def rule_based_candidates(brand: str, product_name: str) -> list[str]:
    brand_norm = normalize_brand(brand)
    product_type = extract_product_type(product_name)
    hero_words = extract_rule_hero_words(product_name, product_type)

    candidates: list[str] = []
    if hero_words and product_type:
        candidates.append(
            normalize_keyword(f"{brand_norm} {' '.join(hero_words[:1])} {product_type}")
        )
        if len(hero_words) > 1:
            candidates.append(
                normalize_keyword(f"{brand_norm} {' '.join(hero_words[:2])} {product_type}")
            )
    if hero_words:
        candidates.append(normalize_keyword(f"{brand_norm} {' '.join(hero_words[:2])}"))
    if product_type:
        candidates.append(normalize_keyword(f"{brand_norm} {product_type}"))

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    return deduped[:3]


def merge_candidates(
    *,
    llm_candidates: list[str],
    rule_candidates: list[str],
    max_candidates: int = 3,
) -> list[tuple[str, str]]:
    merged: list[tuple[str, str]] = []
    seen: set[str] = set()

    for source, items in (("llm", llm_candidates), ("rule", rule_candidates)):
        for keyword in items:
            normalized = normalize_keyword(keyword)
            if not normalized or normalized in seen:
                continue
            merged.append((normalized, source))
            seen.add(normalized)
            if len(merged) >= max_candidates:
                return merged
    return merged


def build_llm_prompt(products: list[dict[str, str]]) -> str:
    examples = json.dumps(FEW_SHOT_EXAMPLES, indent=2)
    payload = json.dumps(products, indent=2)
    return textwrap.dedent(
        f"""
        You generate natural Google Trends search phrases for Sephora skincare products.

        For each product, return:
        - hero_words: 1-2 distinctive branded or product-specific words people might search
          (examples: vinoperfect, superberry, green tea, watermelon, argan, nmf, beauty elixir)
        - product_type: one short function term if obvious (serum, cleanser, lip mask, sunscreen,
          toner, mist, moisturizer, oil, peel, balm, eye cream)
        - candidates: 2-3 lowercase Google search phrases, ordered best-first

        Rules:
        - Phrases should match what a shopper would type into Google, not the full Sephora title.
        - Max 5 words after the brand name.
        - Drop percentages, "100 percent", "pure", "intense hydration", "with vitamin c",
          sizes, and marketing fluff.
        - ALWAYS include the product-type noun (oil, pads, cleanser, serum, mask, etc.) in
          every candidate. Never strip it: "josie maran argan oil" not "josie maran argan";
          "dr dennis gross peel pads" not "dr dennis gross daily peel".
        - ALWAYS keep the word "mini" when the product name includes mini, and place it right
          after the brand: "tatcha mini rice cleanser", "la mer mini cream".
        - Do not include the brand name twice. Spell the brand correctly. Do not split
          possessives: write "kiehls", not "kiehl s".
        - Prefer shorter, high-intent phrases over long literal titles, but keep the hero word
          AND the type noun.
        - Good patterns: brand + hero + type, brand + type, brand + hero + type variant.
          Example: "glow recipe watermelon toner" beats "glow recipe watermelon glow pha bha pore tight toner".

        Examples:
        {examples}

        Products:
        {payload}

        Return JSON only:
        {{
          "products": [
            {{
              "product_id": "...",
              "hero_words": ["..."],
              "product_type": "serum",
              "candidates": ["brand hero serum", "brand hero", "brand serum"]
            }}
          ]
        }}
        """
    ).strip()


def parse_llm_response(content: str) -> list[dict[str, Any]]:
    payload = json.loads(content)
    products = payload.get("products", payload)
    if not isinstance(products, list):
        raise ValueError("LLM response must contain a products list.")
    return products
