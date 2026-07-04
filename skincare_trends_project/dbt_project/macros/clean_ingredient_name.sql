{% macro clean_ingredient_name(column) %}
    {%- if target.type == 'bigquery' -%}
        {%- set ns = namespace(expr=column) -%}
        {%- for i in range(2) -%}
            {%- set ns.expr = "TRIM(REGEXP_REPLACE(TRIM(" ~ ns.expr ~ "), r'[\\s\\.\\\"\\'\\]\\*:\\-,]+', ''))" -%}
        {%- endfor -%}
        {%- for i in range(2) -%}
            {%- set ns.expr = "TRIM(REGEXP_REPLACE(TRIM(" ~ ns.expr ~ "), r'^[\\s\\.\\\"\\'\\]\\*:\\-,]+', ''))" -%}
        {%- endfor -%}
        LOWER(TRIM({{ ns.expr }}))
    {%- else -%}
        {%- set ns = namespace(expr=column) -%}
        {%- for i in range(2) -%}
            {%- set ns.expr = "TRIM(REGEXP_REPLACE(TRIM(" ~ ns.expr ~ "), $$[\\s\\.\\\"'\\]\\*:\\-,]+$$, '', 'g'))" -%}
        {%- endfor -%}
        {%- for i in range(2) -%}
            {%- set ns.expr = "TRIM(REGEXP_REPLACE(TRIM(" ~ ns.expr ~ "), $$^[\\s\\.\\\"'\\]\\*:\\-,]+$$, '', 'g'))" -%}
        {%- endfor -%}
        LOWER(TRIM({{ ns.expr }}))
    {%- endif -%}
{% endmacro %}
