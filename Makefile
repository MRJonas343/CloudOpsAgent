.PHONY: install lint format test up down build clean

install:
	uv sync --directory services/app
	uv sync --directory services/agent

lint:
	uv run --directory services/agent ruff check .

format:
	uv run --directory services/agent ruff format .

test:
	uv run --directory services/agent pytest

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

clean:
	rm -rf services/app/.venv services/agent/.venv
	rm -rf services/agent/.pytest_cache services/agent/.ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
