{% macro config_partitioned_trends(cluster_by, partition_field='date') %}
    {%- if target.type == 'bigquery' -%}
        {# BQ sandbox caps partition expiration at 60 days, which drops older trend weeks.
           Use unpartitioned tables until billing is enabled; then add partition_by + expiration. #}
        {{ config(materialized='table') }}
    {%- else -%}
        {{ config(materialized='table') }}
    {%- endif -%}
{% endmacro %}
