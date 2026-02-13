.PHONY: help install dev test lint typecheck format build clean docker-build docker-test publish run docs docs-serve docs-build setup quickstart preflight doctor init

PYTHON := python
PIP := pip
PYTEST := pytest
DOCKER := docker
DOCKER_COMPOSE := docker-compose

PROJECT_NAME := venomqa
VERSION := $(shell $(PYTHON) -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])" 2>/dev/null || echo "0.1.0")

help:
	@echo "VenomQA - Available targets:"
	@echo ""
	@echo "  Quick Start:"
	@echo "    setup          One-click setup (Python script)"
	@echo "    quickstart     Quick setup (Bash script)"
	@echo "    init           Initialize a new VenomQA project"
	@echo "    preflight      Run preflight checks"
	@echo "    doctor         Run system health checks"
	@echo ""
	@echo "  Development:"
	@echo "    install        Install dependencies"
	@echo "    dev            Install development dependencies"
	@echo "    run            Run the CLI"
	@echo ""
	@echo "  Testing:"
	@echo "    test           Run all tests"
	@echo "    test-unit      Run unit tests only"
	@echo "    test-integration Run integration tests"
	@echo "    test-coverage  Run tests with coverage"
	@echo "    test-docker    Run tests in Docker"
	@echo ""
	@echo "  Code Quality:"
	@echo "    lint           Run ruff linting"
	@echo "    typecheck      Run mypy type checking"
	@echo "    format         Format code with black"
	@echo "    format-check   Check code formatting"
	@echo ""
	@echo "  Documentation:"
	@echo "    docs           Serve documentation locally"
	@echo "    docs-serve     Serve documentation locally (http://localhost:8000)"
	@echo "    docs-build     Build documentation"
	@echo ""
	@echo "  Build & Package:"
	@echo "    build          Build package"
	@echo "    clean          Clean build artifacts"
	@echo ""
	@echo "  Docker:"
	@echo "    docker-build   Build Docker image"
	@echo "    docker-test    Run tests in Docker Compose"
	@echo "    docker-push    Push Docker image"
	@echo ""
	@echo "  Kubernetes:"
	@echo "    k8s-apply      Apply K8s manifests"
	@echo "    k8s-delete     Delete K8s resources"
	@echo ""
	@echo "  Publishing:"
	@echo "    publish        Publish to PyPI"
	@echo "    publish-test   Publish to TestPyPI"
	@echo ""
	@echo "  Reports:"
	@echo "    report         Generate test reports"

# Quick Start targets
setup:
	$(PYTHON) setup.py

quickstart:
	./scripts/quickstart.sh

init:
	venomqa init --with-sample

preflight:
	venomqa preflight

doctor:
	venomqa doctor

# Installation targets
install:
	$(PIP) install -e .

dev:
	$(PIP) install -e ".[dev]"

test:
	$(PYTEST) tests/ -v --tb=short

test-unit:
	$(PYTEST) tests/ -v --tb=short -k "not integration and not stress"

test-integration:
	$(PYTEST) tests/test_integration.py -v --tb=short

test-coverage:
	$(PYTEST) tests/ -v --tb=short \
		--cov=venomqa \
		--cov-report=term-missing \
		--cov-report=html:reports/coverage \
		--cov-fail-under=80

test-docker:
	$(DOCKER_COMPOSE) -f docker/docker-compose.test.yml up --build --abort-on-container-exit

lint:
	ruff check venomqa tests

typecheck:
	mypy venomqa --strict

format:
	black venomqa tests

format-check:
	black --check venomqa tests

build: clean
	$(PYTHON) -m build

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf .coverage
	rm -rf reports/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

docker-build:
	$(DOCKER) build -t $(PROJECT_NAME):$(VERSION) -t $(PROJECT_NAME):latest .

docker-build-test:
	$(DOCKER) build -f docker/Dockerfile.test -t $(PROJECT_NAME)-test:$(VERSION) .

docker-test: docker-build-test
	$(DOCKER_COMPOSE) -f docker/docker-compose.test.yml up --build --abort-on-container-exit

docker-push: docker-build
	$(DOCKER) tag $(PROJECT_NAME):$(VERSION) $(DOCKER_REGISTRY)/$(PROJECT_NAME):$(VERSION)
	$(DOCKER) tag $(PROJECT_NAME):latest $(DOCKER_REGISTRY)/$(PROJECT_NAME):latest
	$(DOCKER) push $(DOCKER_REGISTRY)/$(PROJECT_NAME):$(VERSION)
	$(DOCKER) push $(DOCKER_REGISTRY)/PROJECT_NAME):latest

k8s-apply:
	kubectl apply -f k8s/configmap.yaml
	kubectl apply -f k8s/deployment.yaml

k8s-delete:
	kubectl delete -f k8s/deployment.yaml --ignore-not-found
	kubectl delete -f k8s/configmap.yaml --ignore-not-found

publish: build
	$(PIP) install twine
	twine upload dist/*

publish-test: build
	$(PIP) install twine
	twine upload --repository testpypi dist/*

report:
	@mkdir -p reports
	bash scripts/generate-report.sh html reports

run:
	$(PYTHON) -m venomqa.cli

docs: docs-serve

docs-serve:
	mkdocs serve

docs-build:
	mkdocs build --strict

docs-deploy:
	mkdocs gh-deploy

ci: lint typecheck test-coverage
	@echo "CI checks passed!"

release: clean lint typecheck test build
	@echo "Release ready! Version: $(VERSION)"
