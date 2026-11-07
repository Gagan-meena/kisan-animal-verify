.PHONY: up down migrate test lint fmt

up:
	cp -n .env.example .env || true
	docker compose up -d --build

down:
	docker compose down

migrate:
	docker compose exec -T postgres psql -U kisan -d kisan -v ON_ERROR_STOP=1 -f /dev/stdin < db/migrations/001_init.sql
	docker compose exec -T postgres psql -U kisan -d kisan -v ON_ERROR_STOP=1 -f /dev/stdin < db/migrations/002_citus.sql
	docker compose exec -T postgres psql -U kisan -d kisan -v ON_ERROR_STOP=1 -f /dev/stdin < db/seed/state_rules.sql

test:
	pytest -q

lint:
	ruff check kisan tests

fmt:
	ruff format kisan tests && ruff check --fix kisan tests
