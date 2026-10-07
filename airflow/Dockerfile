# Airflow image with the providers the NHL DAGs need, baked in at build time
# (instead of _PIP_ADDITIONAL_REQUIREMENTS, which reinstalls them on every container start).
FROM apache/airflow:3.3.1

# Pinning apache-airflow stops pip from upgrading Airflow itself while resolving the providers
RUN pip install --no-cache-dir \
    "apache-airflow==3.3.1" \
    apache-airflow-providers-snowflake \
    apache-airflow-providers-dbt-cloud
