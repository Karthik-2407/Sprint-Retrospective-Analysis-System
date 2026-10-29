# Makefile for DORA Metrics Analytics Platform
# All targets from CLAUDE.md §10

.PHONY: help bootstrap lint fmt typecheck test test-unit test-int cov migrate migration up down logs seed audit docs ci clean

# Default target
help:
	@echo "DORA Metrics Analytics Platform - Make Targets"
	@echo ""
	@echo "Setup:"
	@echo "  bootstrap    - Install dependencies and pre-commit hooks"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint         - Run ruff linter"
	@echo "  fmt          - Run ruff formatter"
	@echo "  typecheck    - Run mypy type checker"
	@echo "  audit        - Run security audits (pip-audit, bandit, gitleaks)"
	@echo ""
	@echo "Testing:"
	@echo "  test         - Run all tests (unit + integration)"
	@echo "  test-unit    - Run unit tests only"
	@echo "  test-int     - Run integration tests only"
	@echo "  cov          - Run tests with coverage report (fails below 80%)"
	@echo ""
	@echo "Database:"
	@echo "  migrate      - Run alembic upgrade head"
	@echo "  migration    - Create new migration (usage: make migration m='message')"
	@echo ""
	@echo "Docker:"
	@echo "  up           - Start all services (docker compose up -d)"
	@echo "  down         - Stop all services (docker compose down)"
	@echo "  logs         - Follow docker compose logs"
	@echo ""
	@echo "Data:"
	@echo "  seed         - Load demo tenant with golden-dataset events"
	@echo ""
	@echo "Documentation:"
	@echo "  docs         - Build and serve docs locally (mkdocs)"
	@echo ""
	@echo "CI/CD:"
	@echo "  ci           - Run full CI pipeline locally (lint, typecheck, test, audit)"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean        - Remove build artifacts and caches"

# Setup
bootstrap:
	uv sync --frozen
	pre-commit install

# Code Quality
lint:
	ruff check .

fmt:
	ruff format .

typecheck:
	mypy src

audit:
	pip-audit
	bandit -r src/dora_platform
	gitleaks detect --source . --verbose

# Testing
test:
	pytest -q

test-unit:
	pytest tests/unit -q

test-int:
	pytest tests/integration -q

cov:
	pytest --cov=src/dora_platform --cov-fail-under=80 --cov-report=term-missing

# Database
migrate:
	alembic upgrade head

migration:
	@if [ -z "$(m)" ]; then echo "Usage: make migration m='message'"; exit 1; fi
	alembic revision --autogenerate -m "$(m)"

# Docker
up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

# Data
seed:
	python scripts/seed.py

# Documentation
docs:
	mkdocs serve

# CI/CD
ci: lint typecheck test audit
	@echo "CI pipeline passed!"

# Maintenance
clean:
	rm -rf .mypy_cache .pytest_cache .ruff_cache htmlcov dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
