.PHONY: help build test deploy clean validate smoke-test

help:
	@echo "Available commands:"
	@echo "  make build       - Build the SAM application"
	@echo "  make test        - Run unit tests with coverage"
	@echo "  make deploy      - Deploy to AWS (dev stage)"
	@echo "  make validate    - Validate SAM template"
	@echo "  make smoke-test  - Run smoke tests against deployment"
	@echo "  make clean       - Clean build artifacts"

build:
	sam build

test:
	python -m pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html

validate:
	sam validate

deploy: validate build
	bash scripts/deploy.sh $(STAGE) $(FalQueueUrl) $(ReplicateQueueUrl)

deploy-staging: validate build
	bash scripts/deploy.sh staging

deploy-prod: validate build
	bash scripts/deploy.sh prod

smoke-test:
	python scripts/smoke-test.py

local-test:
	sam local start-lambda &
	sleep 5
	sam local invoke RoutingManagerFunction -e tests/events/sample_video_job.json

clean:
	rm -rf .aws-sam/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf __pycache__/
	rm -rf src/__pycache__/
	rm -rf tests/__pycache__/
	find . -name "*.pyc" -delete

install-dev:
	pip install -r requirements.txt

format:
	black src/ tests/
	isort src/ tests/

lint:
	flake8 src/ tests/
	mypy src/