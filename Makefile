.PHONY: sync up down logs init-db load test lint

sync:            ## create .venv from uv.lock
	uv sync

up:              ## start Airflow, warehouse-db and Grafana
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f airflow-scheduler

init-db:         ## apply sql/*.sql to $$WAREHOUSE_URL (local, outside Docker)
	uv run python -m food_prices.run_local --init-schema

load:            ## usage: make load FILE=data/landing/KEN_RTFP_mkt_2007_2026-08-24.csv
	uv run python -m food_prices.run_local --file $(FILE)

test:
	uv run pytest

lint:
	uv run ruff check . && uv run ruff format --check .
