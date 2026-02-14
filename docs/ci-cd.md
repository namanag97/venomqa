# VenomQA CI/CD Integration Guide

This guide covers how to integrate VenomQA into your CI/CD pipelines for automated journey testing.

## Table of Contents

- [Overview](#overview)
- [Exit Codes](#exit-codes)
- [GitHub Actions](#github-actions)
- [GitLab CI](#gitlab-ci)
- [Docker-based Runner](#docker-based-runner)
- [Other CI Systems](#other-ci-systems)
- [Best Practices](#best-practices)
- [Handling Secrets](#handling-secrets)
- [Parallelization Strategies](#parallelization-strategies)
- [Troubleshooting](#troubleshooting)

## Overview

VenomQA is designed for CI/CD environments with proper exit codes, report generation, and configurable timeouts. The CLI returns meaningful exit codes that CI systems can use to determine build success or failure.

### Key Features for CI/CD

- **Proper Exit Codes**: Clear indication of success, failure, or configuration errors
- **Multiple Report Formats**: JUnit XML, HTML, JSON, and Markdown
- **Docker Support**: Pre-built runner image for consistent environments
- **Parallel Execution**: Run journey groups in parallel for faster feedback
- **Service Orchestration**: Integration with Docker Compose for test dependencies

## Exit Codes

VenomQA uses standard exit codes for CI/CD integration:

| Exit Code | Meaning | CI Action |
|-----------|---------|-----------|
| `0` | All journeys passed | Build succeeds |
| `1` | Some journeys failed | Build fails |
| `2` | Configuration error | Build fails (setup issue) |

Example usage in shell scripts:

```bash
venomqa run --config qa/venomqa.yaml
EXIT_CODE=$?

case $EXIT_CODE in
    0)
        echo "All journeys passed!"
        ;;
    1)
        echo "Some journeys failed - check reports"
        exit 1
        ;;
    2)
        echo "Configuration error - check venomqa.yaml"
        exit 2
        ;;
esac
```

## GitHub Actions

### Basic Setup

Create `.github/workflows/venomqa.yml`:

```yaml
name: VenomQA Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_USER: qa
          POSTGRES_PASSWORD: ${{ secrets.QA_DB_PASSWORD }}
          POSTGRES_DB: venomqa_qa
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U qa"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install VenomQA
        run: pip install venomqa[all]

      - name: Start application
        run: docker compose up -d --wait

      - name: Run journeys
        run: |
          venomqa run --config qa/venomqa.yaml

      - name: Generate reports
        if: always()
        run: |
          mkdir -p reports
          venomqa report --format junit --output reports/junit.xml
          venomqa report --format html --output reports/report.html

      - name: Upload reports
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: venomqa-reports
          path: reports/
```

### Parallel Journey Groups

For larger test suites, run journey groups in parallel:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        group: [auth, checkout, api, content]

    steps:
      - uses: actions/checkout@v4

      - name: Run ${{ matrix.group }} journeys
        run: |
          venomqa run ${{ matrix.group }}_* --config qa/venomqa.yaml
```

### Full Example

See `.github/workflows/venomqa.yml.example` for a complete workflow with:
- Configuration validation
- Parallel test execution
- Artifact collection
- JUnit report publishing
- Conditional deployment

## GitLab CI

### Basic Setup

Create `.gitlab-ci.yml`:

```yaml
stages:
  - test
  - deploy

variables:
  POSTGRES_USER: qa
  POSTGRES_PASSWORD: $QA_DB_PASSWORD
  POSTGRES_DB: venomqa_qa

test:
  stage: test
  image: python:3.12
  services:
    - postgres:15-alpine
    - redis:7-alpine
  script:
    - pip install venomqa[all]
    - venomqa run --config qa/venomqa.yaml
    - venomqa report --format junit --output reports/junit.xml
  artifacts:
    when: always
    paths:
      - reports/
    reports:
      junit: reports/junit.xml
```

### Parallel Groups with GitLab

```yaml
.test-template:
  stage: test
  image: python:3.12
  services:
    - postgres:15-alpine
  before_script:
    - pip install venomqa[all]
  artifacts:
    when: always
    reports:
      junit: reports/junit-*.xml

test-auth:
  extends: .test-template
  script:
    - venomqa run auth_* --config qa/venomqa.yaml
    - venomqa report --format junit --output reports/junit-auth.xml

test-checkout:
  extends: .test-template
  script:
    - venomqa run checkout_* --config qa/venomqa.yaml
    - venomqa report --format junit --output reports/junit-checkout.xml
```

### Full Example

See `.gitlab-ci.yml.example` for a complete pipeline with:
- Multi-stage workflow
- Parallel job execution
- GitLab Pages for reports
- Environment-based deployment

## Docker-based Runner

VenomQA provides a Docker image that can run in any CI system.

### Building the Runner Image

```bash
# Build the runner image
docker build -f docker/Dockerfile.runner -t venomqa-runner:latest .

# Or use multi-stage for smaller image
docker build -f docker/Dockerfile.runner --target production -t venomqa-runner:prod .
```

### Using the Runner

```bash
# Run journeys with mounted volumes
docker run --rm \
  -e API_BASE_URL=http://host.docker.internal:8000 \
  -v $(pwd)/qa:/app/qa:ro \
  -v $(pwd)/reports:/app/reports \
  venomqa-runner:latest \
  run --config qa/venomqa.yaml
```

### Docker Compose Integration

```yaml
version: "3.8"

services:
  api:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - postgres

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: qa
      POSTGRES_PASSWORD: qapass
      POSTGRES_DB: qa

  venomqa:
    image: venomqa-runner:latest
    environment:
      - API_BASE_URL=http://api:8000
      - WAIT_FOR_POSTGRES=postgres:5432
      - WAIT_FOR_HTTP=http://api:8000/health
    volumes:
      - ./qa:/app/qa:ro
      - ./reports:/app/reports
    depends_on:
      - api
    command: ["run", "--config", "qa/venomqa.yaml"]
```

### Helper Scripts

The runner image includes helper scripts:

**wait-for-services.sh**: Wait for dependencies before running tests

```bash
docker run --rm venomqa-runner:latest \
  /usr/local/bin/wait-for-services.sh \
    --postgres db:5432 \
    --redis cache:6379 \
    --http http://api:8000/health \
    -- venomqa run
```

**run-journeys.sh**: Comprehensive test runner with reports

```bash
docker run --rm \
  -e WAIT_FOR_POSTGRES=db:5432 \
  -e VENOMQA_CONFIG=qa/venomqa.yaml \
  -v ./qa:/app/qa:ro \
  -v ./reports:/app/reports \
  venomqa-runner:latest \
  /usr/local/bin/run-journeys.sh
```

## Other CI Systems

### Jenkins

```groovy
pipeline {
    agent {
        docker {
            image 'venomqa-runner:latest'
        }
    }

    environment {
        API_BASE_URL = 'http://localhost:8000'
    }

    stages {
        stage('Test') {
            steps {
                sh 'venomqa run --config qa/venomqa.yaml'
            }
            post {
                always {
                    sh 'venomqa report --format junit --output reports/junit.xml'
                    junit 'reports/junit.xml'
                    archiveArtifacts artifacts: 'reports/**'
                }
            }
        }
    }
}
```

### CircleCI

```yaml
version: 2.1

jobs:
  test:
    docker:
      - image: python:3.12
      - image: postgres:15-alpine
        environment:
          POSTGRES_USER: qa
          POSTGRES_PASSWORD: qapass
          POSTGRES_DB: qa
    steps:
      - checkout
      - run:
          name: Install VenomQA
          command: pip install venomqa[all]
      - run:
          name: Run journeys
          command: venomqa run --config qa/venomqa.yaml
      - run:
          name: Generate reports
          command: venomqa report --format junit --output reports/junit.xml
          when: always
      - store_test_results:
          path: reports
      - store_artifacts:
          path: reports

workflows:
  test:
    jobs:
      - test
```

### Azure DevOps

```yaml
trigger:
  - main

pool:
  vmImage: 'ubuntu-latest'

services:
  postgres:
    image: postgres:15-alpine
    ports:
      - 5432:5432

steps:
  - task: UsePythonVersion@0
    inputs:
      versionSpec: '3.12'

  - script: pip install venomqa[all]
    displayName: Install VenomQA

  - script: venomqa run --config qa/venomqa.yaml
    displayName: Run Journeys

  - script: |
      venomqa report --format junit --output $(Build.ArtifactStagingDirectory)/junit.xml
    displayName: Generate Reports
    condition: always()

  - task: PublishTestResults@2
    inputs:
      testResultsFormat: 'JUnit'
      testResultsFiles: '$(Build.ArtifactStagingDirectory)/junit.xml'
    condition: always()
```

### Buildkite

```yaml
steps:
  - label: ":snake: VenomQA Tests"
    command:
      - pip install venomqa[all]
      - venomqa run --config qa/venomqa.yaml
      - venomqa report --format junit --output reports/junit.xml
    plugins:
      - docker-compose#v4.0.0:
          services:
            - postgres
            - redis
    artifact_paths:
      - "reports/**"
```

## Best Practices

### 1. Fail Fast in Development, Full Run in CI

```yaml
# Development - stop on first failure for quick feedback
venomqa run --fail-fast --config qa/venomqa.yaml

# CI - run all tests for complete picture
venomqa run --config qa/venomqa.yaml
```

### 2. Use Journey Groups for Parallelization

Organize journeys by domain:
```
qa/journeys/
  auth_login.py
  auth_registration.py
  checkout_basic.py
  checkout_with_coupon.py
  api_crud.py
  api_versioning.py
```

Then run groups in parallel:
```yaml
matrix:
  group: [auth, checkout, api]
```

### 3. Generate Multiple Report Formats

```bash
# JUnit for CI integration
venomqa report --format junit --output reports/junit.xml

# HTML for human review
venomqa report --format html --output reports/report.html

# JSON for custom processing
venomqa report --format json --output reports/results.json
```

### 4. Set Appropriate Timeouts

```yaml
# venomqa.yaml
timeout: 30  # Default request timeout

# For specific slow operations, override in journey
steps:
  - name: process_large_file
    action: upload.process
    timeout: 120  # 2 minutes for this step
```

### 5. Use Health Checks

Always wait for services before running tests:

```yaml
services:
  api:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 5
```

### 6. Capture Logs on Failure

```yaml
- name: Collect logs on failure
  if: failure()
  run: |
    docker compose logs > reports/docker.log
    docker ps -a > reports/containers.txt
```

## Handling Secrets

### Environment Variables

Never commit secrets to code. Use CI/CD secret management:

**GitHub Actions:**
```yaml
env:
  DATABASE_URL: ${{ secrets.DATABASE_URL }}
  API_KEY: ${{ secrets.API_KEY }}
```

**GitLab CI:**
```yaml
variables:
  DATABASE_URL: $DB_URL  # CI/CD variable
```

### Secret Files

For complex secrets (certificates, key files):

```yaml
# GitHub Actions
- name: Setup credentials
  run: |
    echo "${{ secrets.SERVICE_ACCOUNT_KEY }}" > /tmp/sa-key.json
    export GOOGLE_APPLICATION_CREDENTIALS=/tmp/sa-key.json
```

### VenomQA Configuration

Reference secrets via environment variables in `venomqa.yaml`:

```yaml
# venomqa.yaml
base_url: ${API_BASE_URL:-http://localhost:8000}

ports:
  - name: database
    adapter_type: postgres
    config:
      host: ${POSTGRES_HOST:-localhost}
      port: ${POSTGRES_PORT:-5432}
      user: ${POSTGRES_USER}
      password: ${POSTGRES_PASSWORD}  # From environment
      database: ${POSTGRES_DB}
```

### Secret Masking

VenomQA automatically masks common secret patterns in logs:
- API keys
- Passwords
- Tokens
- Authorization headers

## Parallelization Strategies

### 1. Journey Group Parallelization

Split journeys by domain/feature:

```yaml
# GitHub Actions
strategy:
  matrix:
    group: [auth, checkout, api, content, realtime]
```

### 2. Test Environment Parallelization

Run against multiple environments:

```yaml
strategy:
  matrix:
    environment: [staging, qa, preview]
    include:
      - environment: staging
        base_url: https://staging.example.com
      - environment: qa
        base_url: https://qa.example.com
```

### 3. Database Sharding

For database-heavy tests, use separate databases:

```yaml
strategy:
  matrix:
    shard: [1, 2, 3, 4]

services:
  postgres:
    image: postgres:15-alpine
    env:
      POSTGRES_DB: qa_shard_${{ matrix.shard }}
```

### 4. Time-based Parallelization

Run different test suites at different times:

```yaml
# Fast tests on every push
on:
  push:
    branches: [main, develop]

# Full test suite nightly
on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM daily
```

## Troubleshooting

### Common Issues

**1. Services not ready**

```
Error: Connection refused to localhost:5432
```

Solution: Use health checks and wait scripts:
```bash
wait-for-services.sh --postgres localhost:5432 -- venomqa run
```

**2. Timeout errors**

```
Error: Request timeout after 30s
```

Solution: Increase timeout in config:
```yaml
timeout: 60  # Increase default timeout
```

**3. Permission errors in Docker**

```
Error: Permission denied: /app/reports
```

Solution: Match user IDs:
```bash
docker run --user $(id -u):$(id -g) ...
```

**4. Exit code not propagated**

Ensure your shell script properly captures exit codes:
```bash
set +e  # Don't exit on error
venomqa run
EXIT_CODE=$?
set -e  # Re-enable exit on error
# ... generate reports ...
exit $EXIT_CODE  # Propagate original exit code
```

### Debugging CI Failures

**1. Enable verbose output:**
```bash
venomqa run --verbose --config qa/venomqa.yaml
```

**2. Add debugging steps:**
```yaml
- name: Debug environment
  if: failure()
  run: |
    env | sort
    docker ps -a
    docker compose logs
    cat qa/venomqa.yaml
```

**3. SSH into failed runner (GitHub Actions):**
```yaml
- name: Debug with tmate
  if: failure()
  uses: mxschmitt/action-tmate@v3
  with:
    limit-access-to-actor: true
```

### Getting Help

- **Documentation**: https://venomqa.dev/docs
- **Issues**: https://github.com/namanag97/venomqa/issues
- **Discussions**: https://github.com/namanag97/venomqa/discussions

---

For complete working examples, see:
- `.github/workflows/venomqa.yml.example` - GitHub Actions
- `.gitlab-ci.yml.example` - GitLab CI
- `docker/Dockerfile.runner` - Docker runner image
