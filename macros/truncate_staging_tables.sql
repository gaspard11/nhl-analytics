{% macro truncate_staging_on_success(results) %}

  {% set failures = results
      | selectattr("status", "in", ["error", "fail", "skipped"])
      | list %}

  {% if failures | length == 0 %}

    {% set get_tables_sql %}
      select table_name
      from NHL_DB.INFORMATION_SCHEMA.TABLES
      where table_schema = 'STAGING'
        and table_type = 'BASE TABLE'
    {% endset %}

    {% set tables = run_query(get_tables_sql) %}

    {% if execute %}
      {% for row in tables.rows %}
        {% set truncate_sql %}
          truncate table NHL_DB.STAGING.{{ row['TABLE_NAME'] }}
        {% endset %}
        {% do run_query(truncate_sql) %}
        {% do log("Truncated NHL_DB.STAGING." ~ row['TABLE_NAME'], info=True) %}
      {% endfor %}
    {% endif %}

  {% else %}
    {% do log("Run had failures — skipping truncate of NHL_DB.STAGING", info=True) %}
  {% endif %}

{% endmacro %}