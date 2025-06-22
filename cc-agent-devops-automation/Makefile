.PHONY: install test build deploy clean setup-github

# Default stage
STAGE ?= dev

install:
	pip install -r requirements.txt
	cd layers && pip install -r requirements.txt -t python/

test:
	pytest tests/ -v

build:
	sam build --template template.yaml

deploy: build
	sam deploy --config-env $(STAGE) --no-confirm-changeset

setup-github:
	./scripts/setup-github.sh

check-workflow:
	./scripts/check-workflow.sh

clean:
	rm -rf .aws-sam/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf layers/python/
	find . -type d -name __pycache__ -exec rm -rf {} +

local-test:
	sam local invoke DevOpsAutomationFunction --event tests/events/health_check.json
	sam local invoke StripeMrrReporterFunction --event tests/events/mrr_calculation.json

smoke-test:
	python scripts/smoke-test.py --stage $(STAGE)