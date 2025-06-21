.PHONY: help install test build deploy smoke-test clean

ENVIRONMENT ?= dev
PYTHON := python3
PIP := pip3

help:
	@echo "Credit Reconciler - Available commands:"
	@echo "  make install      - Install dependencies"
	@echo "  make test        - Run unit tests"
	@echo "  make build       - Build SAM application"
	@echo "  make deploy      - Deploy to AWS (ENVIRONMENT=dev|staging|prod)"
	@echo "  make smoke-test  - Run smoke tests"
	@echo "  make clean       - Clean build artifacts"

install:
	$(PIP) install -r requirements.txt

test:
	$(PYTHON) -m pytest tests/ -v --cov=src --cov-report=term-missing

build:
	sam build --use-container

deploy:
	./scripts/deploy.sh $(ENVIRONMENT)

smoke-test:
	$(PYTHON) scripts/smoke-test.py --env $(ENVIRONMENT)

clean:
	rm -rf .aws-sam/
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -f .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Combined commands
deploy-and-test: deploy smoke-test

# Development workflow
dev: install test build deploy-and-test