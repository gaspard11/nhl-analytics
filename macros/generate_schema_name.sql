{#
    Production jobs write to the custom schema as-is (e.g. MARTS).
    Everything else (IDE, CI, local dbt Core) writes to <target schema>_<custom schema>
    (e.g. DBT_RGASPARD_MARTS), so it can never overwrite production tables.
    DBT_CLOUD_INVOCATION_CONTEXT is set by dbt Cloud: prod, staging, ci or dev.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set is_prod = env_var('DBT_CLOUD_INVOCATION_CONTEXT', 'dev') == 'prod' -%}

    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- elif is_prod -%}
        {{ custom_schema_name | trim }}
    {%- else -%}
        {{ target.schema }}_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}