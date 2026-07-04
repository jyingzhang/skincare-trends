{% macro split_string(column, delimiter) %}
    {%- if target.type == 'bigquery' -%}
        SPLIT({{ column }}, {{ delimiter }})
    {%- else -%}
        STRING_SPLIT({{ column }}, {{ delimiter }})
    {%- endif -%}
{% endmacro %}

{% macro cross_join_unnest_split(column, delimiter, alias) %}
    {%- if target.type == 'bigquery' -%}
        CROSS JOIN UNNEST({{ split_string(column, delimiter) }}) AS {{ alias }}
    {%- else -%}
        , UNNEST({{ split_string(column, delimiter) }}) AS _u({{ alias }})
    {%- endif -%}
{% endmacro %}

{% macro unnest_col(alias) %}
    {%- if target.type == 'bigquery' -%}
        {{ alias }}
    {%- else -%}
        _u.{{ alias }}
    {%- endif -%}
{% endmacro %}

{% macro select_unnest_split(source_column, delimiter, output_column) %}
    {%- if target.type == 'bigquery' -%}
        SELECT
            product_id,
            {{ output_column }}
        FROM {{ ref('stg_sephora_products') }}
        CROSS JOIN UNNEST({{ split_string(source_column, delimiter) }}) AS {{ output_column }}
        WHERE ingredients IS NOT NULL
    {%- else -%}
        SELECT
            product_id,
            UNNEST({{ split_string(source_column, delimiter) }}) AS {{ output_column }}
        FROM {{ ref('stg_sephora_products') }}
        WHERE ingredients IS NOT NULL
    {%- endif -%}
{% endmacro %}

{% macro first_n_words(column, word_count) %}
    {%- if target.type == 'bigquery' -%}
        ARRAY_TO_STRING(
            ARRAY_SLICE(SPLIT(TRIM({{ column }}), ' '), 0, {{ word_count }}),
            ' '
        )
    {%- else -%}
        ARRAY_TO_STRING(
            LIST_SLICE(STRING_SPLIT(TRIM({{ column }}), ' '), 1, {{ word_count }}),
            ' '
        )
    {%- endif -%}
{% endmacro %}

{% macro string_agg_distinct(column, delimiter) %}
    {%- if target.type == 'bigquery' -%}
        STRING_AGG(DISTINCT {{ column }}, {{ delimiter }})
    {%- else -%}
        ARRAY_TO_STRING(LIST(DISTINCT {{ column }}), {{ delimiter }})
    {%- endif -%}
{% endmacro %}

{% macro regexp_replace_all(expression, pattern, replacement) %}
    {%- if target.type == 'bigquery' -%}
        REGEXP_REPLACE({{ expression }}, r'{{ pattern }}', r'{{ replacement }}')
    {%- else -%}
        REGEXP_REPLACE({{ expression }}, '{{ pattern }}', '{{ replacement }}', 'g')
    {%- endif -%}
{% endmacro %}

{% macro regexp_replace_ci(expression, pattern, replacement) %}
    {%- if target.type == 'bigquery' -%}
        REGEXP_REPLACE({{ expression }}, r'(?i){{ pattern }}', r'{{ replacement }}')
    {%- else -%}
        REGEXP_REPLACE({{ expression }}, '{{ pattern }}', '{{ replacement }}', 'i')
    {%- endif -%}
{% endmacro %}

{% macro ilike_contains(column, pattern) %}
    {%- if target.type == 'bigquery' -%}
        LOWER({{ column }}) LIKE LOWER({{ pattern }})
    {%- else -%}
        {{ column }} ILIKE {{ pattern }}
    {%- endif -%}
{% endmacro %}

{% macro cast_trend_date(column) %}
    {%- if target.type == 'bigquery' -%}
        DATE({{ column }})
    {%- else -%}
        CAST({{ column }} AS DATE)
    {%- endif -%}
{% endmacro %}

{% macro date_trunc_month(column) %}
    {%- if target.type == 'bigquery' -%}
        DATE_TRUNC(CAST({{ column }} AS DATE), MONTH)
    {%- else -%}
        DATE_TRUNC('month', CAST({{ column }} AS DATE))
    {%- endif -%}
{% endmacro %}

{% macro date_midpoint(start_date, end_date) %}
    {%- if target.type == 'bigquery' -%}
        DATE_ADD(
            {{ start_date }},
            INTERVAL CAST(DIV(DATE_DIFF({{ end_date }}, {{ start_date }}, DAY), 2) AS INT64) DAY
        )
    {%- else -%}
        {{ start_date }} + (({{ end_date }} - {{ start_date }}) / 2)
    {%- endif -%}
{% endmacro %}

{% macro months_before(date_column, months) %}
    {%- if target.type == 'bigquery' -%}
        DATE_SUB({{ date_column }}, INTERVAL {{ months }} MONTH)
    {%- else -%}
        {{ date_column }} - INTERVAL {{ months }} MONTH
    {%- endif -%}
{% endmacro %}

{% macro stddev(column) %}
    {%- if target.type == 'bigquery' -%}
        STDDEV_SAMP({{ column }})
    {%- else -%}
        STDDEV({{ column }})
    {%- endif -%}
{% endmacro %}

{% macro rating_counts_array() %}
    {%- if target.type == 'bigquery' -%}
        ARRAY_AGG(STRUCT(rating AS rating, count AS count) ORDER BY rating)
    {%- else -%}
        LIST(STRUCT_PACK(rating := rating, count := count))
    {%- endif -%}
{% endmacro %}
