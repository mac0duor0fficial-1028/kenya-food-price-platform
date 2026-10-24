# Airflow image with this project installed via uv, constrained to Airflow's tested dependency set.
FROM apache/airflow:2.10.5-python3.12

ARG AIRFLOW_VERSION=2.10.5
ARG PYTHON_VERSION=3.12

COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/uv

USER root
COPY pyproject.toml README.md /opt/airflow/project/
COPY src /opt/airflow/project/src
# --system installs into the image's interpreter; the constraints file keeps pandas/SQLAlchemy/
# pyarrow at the versions Airflow was tested with.
RUN uv pip install --system \
      --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt" \
      /opt/airflow/project \
 && chown -R airflow:root /opt/airflow/project
USER airflow
