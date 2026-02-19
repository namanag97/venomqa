---
title: "CI/CD API Testing: Setting Up Automated API Testing in GitHub Actions, GitLab CI, and Jenkins"
description: "A complete guide to integrating API testing into your CI/CD pipeline. Learn to set up VenomQA, Schemathesis, and other tools in GitHub Actions, GitLab CI, and Jenkins with Docker Compose test environments and automated reporting."
authors:
  - Naman Agarwal
date: 2024-02-15
categories:
  - CI/CD
  - API Testing
  - DevOps
tags:
  - CI/CD testing
  - automated API testing
  - continuous testing
  - GitHub Actions
  - GitLab CI
  - Jenkins
  - Docker Compose
  - API testing automation
cover_image: /assets/images/blog/ci-cd-api-testing.png
---

# CI/CD API Testing: From Local to Production

API testing in CI/CD is the difference between catching bugs before they ship and waking up to production incidents at 3 AM.

This guide covers everything you need to set up comprehensive API testing in your CI/CD pipeline:

- Test environment setup with Docker Compose
- GitHub Actions, GitLab CI, and Jenkins configurations
- Test reporting and notifications
- Strategies for different testing phases

## The CI/CD Testing Landscape

### Testing Stages

```
┌─────────────────────────────────────────────────────────────────┐
│                        CI/CD Pipeline                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Commit ──► Build ──► Unit Tests ──► API Tests ──► Deploy       │
│                           │              │                       │
│                           │              ├── Contract Tests      │
│                           │              ├── Integration Tests   │
│                           │              └── Workflow Tests      │
│                           │                                      │
│                        < 5 min       5-30 min                    │
└─────────────────────────────────────────────────────────────────┘
```

### Testing Types in CI

| Test Type | Speed | Coverage | When to Run |
|-----------|-------|----------|-------------|
| **Unit Tests** | Fast (seconds) | Individual functions | Every commit |
| **Contract Tests** | Medium (1-5 min) | API schema compliance | Every PR |
| **Integration Tests** | Medium (5-15 min) | Service interactions | Every PR |
| **Workflow Tests** | Slower (15-30 min) | End-to-end sequences | Nightly / main branch |
| **Performance Tests** | Slow (30+ min) | Load and latency | Weekly / releases |

## Test Environment Setup

### Docker Compose for CI

Create a reproducible test environment:

```yaml
# docker-compose.test.yml
version: '3.8'

services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://test:test@postgres:5432/testdb
      - REDIS_URL=redis://redis:6379
      - ENVIRONMENT=testing
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 5s
      timeout: 3s
      retries: 10

  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_USER=test
      - POSTGRES_PASSWORD=test
      - POSTGRES_DB=testdb
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test -d testdb"]
      interval: 2s
      timeout: 2s
      retries: 10

  redis:
    image: redis:7-alpine

  # Test runner container
  test-runner:
    build:
      context: .
      dockerfile: Dockerfile.test
    environment:
      - API_URL=http://api:8000
      - DATABASE_URL=postgresql://test:test@postgres:5432/testdb
    depends_on:
      api:
        condition: service_healthy
    volumes:
      - ./test-results:/results
```

### Test Runner Dockerfile

```dockerfile
# Dockerfile.test
FROM python:3.11-slim

WORKDIR /app

# Install test dependencies
COPY requirements-test.txt .
RUN pip install --no-cache-dir -r requirements-test.txt

# Copy test configuration
COPY venomqa.yaml .
COPY tests/ ./tests/

# Default command
CMD ["venomqa", "run", "--config", "venomqa.yaml", "--output", "/results"]
```

### VenomQA Configuration for CI

```yaml
# venomqa.yaml
api:
  base_url: ${API_URL:-http://localhost:8000}
  timeout: 30

database:
  url: ${DATABASE_URL:-postgresql://test:test@localhost:5432/testdb}
  
actions:
  - name: create_order
    method: POST
    path: /orders
    body:
      amount: 100
      product_id: 1
    capture:
      order_id: "$.id"
  
  - name: refund_order
    method: POST
    path: /orders/{order_id}/refund
    requires:
      - order_id
  
  - name: cancel_order
    method: POST
    path: /orders/{order_id}/cancel
    requires:
      - order_id

invariants:
  - name: no_500_errors
    severity: critical
    check: "response.status < 500"
  
  - name: response_time_under_5s
    severity: warning
    check: "response.time < 5000"

exploration:
  strategy: bfs
  max_steps: 500
  max_depth: 10

reporting:
  output_dir: /results
  formats:
    - json
    - html
    - junit
```

## GitHub Actions Configuration

### Basic API Testing Workflow

```yaml
# .github/workflows/api-tests.yml
name: API Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  contract-tests:
    name: Contract Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          pip install schemathesis
      
      - name: Start API
        run: |
          docker-compose -f docker-compose.test.yml up -d api postgres
          sleep 10
      
      - name: Run contract tests
        run: |
          st run http://localhost:8000/openapi.json \
            --checks all \
            --max-examples 100 \
            --report junit.xml \
            --report-html report/
      
      - name: Upload results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: contract-test-results
          path: |
            junit.xml
            report/
      
      - name: Cleanup
        if: always()
        run: docker-compose -f docker-compose.test.yml down -v

  workflow-tests:
    name: Workflow Tests (VenomQA)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      
      - name: Install VenomQA
        run: pip install venomqa
      
      - name: Run test environment
        run: |
          docker-compose -f docker-compose.test.yml up -d
          sleep 15  # Wait for services to be healthy
      
      - name: Run VenomQA exploration
        run: |
          venomqa run \
            --api-url http://localhost:8000 \
            --database-url postgresql://test:test@localhost:5432/testdb \
            --max-steps 500 \
            --output ./results
      
      - name: Upload VenomQA report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: venomqa-report
          path: results/
      
      - name: Check for violations
        run: |
          if [ -f results/violations.json ] && [ -s results/violations.json ]; then
            echo "::error::VenomQA found invariant violations"
            cat results/violations.json
            exit 1
          fi
      
      - name: Cleanup
        if: always()
        run: docker-compose -f docker-compose.test.yml down -v
```

### Advanced GitHub Actions with Matrix

```yaml
# .github/workflows/api-tests-matrix.yml
name: API Tests (Matrix)

on:
  push:
    branches: [main]
  schedule:
    - cron: '0 2 * * *'  # Nightly at 2 AM

jobs:
  workflow-tests:
    name: Workflow Tests - ${{ matrix.config.name }}
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        config:
          - name: Shallow Exploration
            max_steps: 200
            max_depth: 5
          - name: Deep Exploration
            max_steps: 1000
            max_depth: 15
          - name: Coverage Guided
            strategy: coverage-guided
            max_steps: 500
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: testdb
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 2s
          --health-timeout 2s
          --health-retries 10

    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
          pip install venomqa
      
      - name: Start API
        run: |
          docker build -t api-test .
          docker run -d --name api \
            -e DATABASE_URL=postgresql://test:test@localhost:5432/testdb \
            -p 8000:8000 \
            api-test
          sleep 10
      
      - name: Run VenomQA
        run: |
          venomqa run \
            --config venomqa.yaml \
            --strategy ${{ matrix.config.strategy || 'bfs' }} \
            --max-steps ${{ matrix.config.max_steps }} \
            --max-depth ${{ matrix.config.max_depth }} \
            --output ./results/${{ matrix.config.name }}
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/testdb
          API_URL: http://localhost:8000
      
      - name: Upload results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: results-${{ matrix.config.name }}
          path: results/
      
      - name: Cleanup
        if: always()
        run: docker stop api && docker rm api

  notify-on-failure:
    name: Notify on Failure
    needs: [workflow-tests]
    if: failure()
    runs-on: ubuntu-latest
    steps:
      - name: Send Slack notification
        uses: slackapi/slack-github-action@v1
        with:
          payload: |
            {
              "text": "API Tests failed in ${{ github.repository }}",
              "blocks": [
                {
                  "type": "section",
                  "text": {
                    "type": "mrkdwn",
                    "text": ":x: *API Tests Failed*\nRepository: ${{ github.repository }}\nBranch: ${{ github.ref_name }}\n<${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}|View Run>"
                  }
                }
              ]
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK }}
```

## GitLab CI Configuration

### Complete GitLab CI Pipeline

```yaml
# .gitlab-ci.yml

stages:
  - build
  - test
  - report
  - deploy

variables:
  POSTGRES_USER: test
  POSTGRES_PASSWORD: test
  POSTGRES_DB: testdb
  DOCKER_TLS_CERTDIR: ""

# Build stage
build-api:
  stage: build
  image: docker:24
  services:
    - docker:24-dind
  script:
    - docker build -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA

# Unit tests
unit-tests:
  stage: test
  image: python:3.11
  script:
    - pip install -e ".[dev]"
    - pytest tests/unit -v --junitxml=reports/unit.xml
  artifacts:
    reports:
      junit: reports/unit.xml
    expire_in: 1 week

# Contract tests with Schemathesis
contract-tests:
  stage: test
  image: python:3.11
  services:
    - name: $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
      alias: api
    - name: postgres:15
      alias: postgres
  variables:
    DATABASE_URL: postgresql://test:test@postgres:5432/testdb
  before_script:
    - pip install schemathesis
    - sleep 15  # Wait for API to start
  script:
    - st run http://api:8000/openapi.json
        --checks all
        --max-examples 100
        --hypothesis-seed=$CI_COMMIT_SHA
        --report junit.xml
        --report-html schemathesis-report/
  artifacts:
    paths:
      - schemathesis-report/
      - junit.xml
    reports:
      junit: junit.xml
    expire_in: 1 week
    when: always

# Workflow tests with VenomQA
workflow-tests:
  stage: test
  image: python:3.11
  services:
    - name: $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
      alias: api
    - name: postgres:15
      alias: postgres
    - name: redis:7
      alias: redis
  variables:
    API_URL: http://api:8000
    DATABASE_URL: postgresql://test:test@postgres:5432/testdb
  before_script:
    - pip install venomqa
    - sleep 15
  script:
    - venomqa run
        --config venomqa.yaml
        --max-steps 500
        --output ./results
    - |
      if [ -f results/violations.json ] && [ -s results/violations.json ]; then
        echo "VenomQA found violations!"
        cat results/violations.json
        exit 1
      fi
  artifacts:
    paths:
      - results/
    expire_in: 1 week
    when: always
  allow_failure: false

# Nightly deep exploration
nightly-workflow-tests:
  stage: test
  image: python:3.11
  services:
    - name: $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
      alias: api
    - name: postgres:15
      alias: postgres
  variables:
    API_URL: http://api:8000
    DATABASE_URL: postgresql://test:test@postgres:5432/testdb
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule"
  before_script:
    - pip install venomqa
    - sleep 15
  script:
    - venomqa run
        --config venomqa.yaml
        --strategy coverage-guided
        --max-steps 2000
        --max-depth 20
        --output ./results/nightly
  artifacts:
    paths:
      - results/
    expire_in: 30 days

# Generate combined report
test-report:
  stage: report
  image: python:3.11
  needs:
    - unit-tests
    - contract-tests
    - workflow-tests
  script:
    - pip install junitparser
    - python scripts/combine_reports.py
  artifacts:
    paths:
      - combined-report/
    expire_in: 30 days
  when: always

# Deploy (only if all tests pass)
deploy-staging:
  stage: deploy
  image: docker:24
  services:
    - docker:24-dind
  rules:
    - if: $CI_COMMIT_BRANCH == "develop"
  needs:
    - build-api
    - unit-tests
    - contract-tests
    - workflow-tests
  script:
    - echo "Deploying to staging..."
    # Add deployment commands here
```

### GitLab CI Templates

Create reusable templates for API testing:

```yaml
# .gitlab/ci/api-testing.yml

.api-test-base:
  image: python:3.11
  services:
    - name: postgres:15
      alias: postgres
  variables:
    POSTGRES_USER: test
    POSTGRES_PASSWORD: test
    POSTGRES_DB: testdb
  before_script:
    - pip install venomqa schemathesis pytest
    - sleep 10

.venomqa-test:
  extends: .api-test-base
  script:
    - venomqa run --config venomqa.yaml --output ./results
    - |
      if [ -f results/violations.json ] && [ -s results/violations.json ]; then
        exit 1
      fi
  artifacts:
    paths:
      - results/
    when: always

.schemathesis-test:
  extends: .api-test-base
  script:
    - st run ${API_URL}/openapi.json --report junit.xml --report-html report/
  artifacts:
    paths:
      - report/
    reports:
      junit: junit.xml
    when: always
```

## Jenkins Pipeline Configuration

### Jenkinsfile for API Testing

```groovy
// Jenkinsfile
pipeline {
    agent {
        docker {
            image 'python:3.11'
            args '--network host'
        }
    }
    
    environment {
        DOCKER_IMAGE = 'api-test'
        COMPOSE_FILE = 'docker-compose.test.yml'
    }
    
    stages {
        stage('Build') {
            steps {
                sh 'docker build -t ${DOCKER_IMAGE} .'
            }
        }
        
        stage('Start Environment') {
            steps {
                sh 'docker-compose -f ${COMPOSE_FILE} up -d'
                sh 'sleep 15'
                sh 'docker-compose -f ${COMPOSE_FILE} ps'
            }
        }
        
        stage('Unit Tests') {
            steps {
                sh 'pip install -e ".[dev]"'
                sh 'pytest tests/unit -v --junitxml=reports/unit.xml'
            }
            post {
                always {
                    junit 'reports/unit.xml'
                }
            }
        }
        
        stage('Contract Tests') {
            steps {
                sh 'pip install schemathesis'
                sh '''
                    st run http://localhost:8000/openapi.json \
                        --checks all \
                        --max-examples 100 \
                        --report junit.xml \
                        --report-html schemathesis-report/
                '''
            }
            post {
                always {
                    junit 'junit.xml'
                    publishHTML([
                        allowMissing: false,
                        alwaysLinkToLastBuild: true,
                        keepAll: true,
                        reportDir: 'schemathesis-report',
                        reportFiles: 'index.html',
                        reportName: 'Schemathesis Report'
                    ])
                }
            }
        }
        
        stage('Workflow Tests') {
            steps {
                sh 'pip install venomqa'
                sh '''
                    venomqa run \
                        --config venomqa.yaml \
                        --max-steps 500 \
                        --output ./results
                '''
            }
            post {
                always {
                    publishHTML([
                        allowMissing: false,
                        alwaysLinkToLastBuild: true,
                        keepAll: true,
                        reportDir: 'results',
                        reportFiles: 'index.html',
                        reportName: 'VenomQA Report'
                    ])
                    
                    script {
                        if (fileExists('results/violations.json')) {
                            def violations = readFile('results/violations.json')
                            if (violations.trim()) {
                                error "VenomQA found invariant violations"
                            }
                        }
                    }
                }
            }
        }
        
        stage('Deploy') {
            when {
                branch 'main'
            }
            steps {
                echo 'Deploying to production...'
                // Add deployment steps
            }
        }
    }
    
    post {
        always {
            sh 'docker-compose -f ${COMPOSE_FILE} down -v'
            cleanWs()
        }
        
        failure {
            mail(
                to: 'team@example.com',
                subject: "API Tests Failed: ${env.JOB_NAME} #${env.BUILD_NUMBER}",
                body: """
                    API tests have failed.
                    
                    Job: ${env.JOB_NAME}
                    Build: ${env.BUILD_NUMBER}
                    URL: ${env.BUILD_URL}
                    
                    Please investigate.
                """
            )
        }
    }
}
```

### Jenkins with Parallel Testing

```groovy
// Jenkinsfile.parallel
pipeline {
    agent any
    
    stages {
        stage('Test') {
            parallel {
                stage('Unit Tests') {
                    agent {
                        docker { image 'python:3.11' }
                    }
                    steps {
                        sh 'pip install -e ".[dev]"'
                        sh 'pytest tests/unit --junitxml=unit.xml'
                    }
                    post {
                        always {
                            junit 'unit.xml'
                        }
                    }
                }
                
                stage('Contract Tests') {
                    agent {
                        docker { image 'python:3.11' }
                    }
                    steps {
                        sh '''
                            docker-compose -f docker-compose.test.yml up -d api postgres
                            sleep 15
                            pip install schemathesis
                            st run http://localhost:8000/openapi.json --report junit.xml
                        '''
                    }
                    post {
                        always {
                            junit 'junit.xml'
                            sh 'docker-compose -f docker-compose.test.yml down -v'
                        }
                    }
                }
                
                stage('Workflow Tests (Shallow)') {
                    agent {
                        docker { image 'python:3.11' }
                    }
                    steps {
                        sh '''
                            docker-compose -f docker-compose.test.yml up -d
                            sleep 15
                            pip install venomqa
                            venomqa run --config venomqa.yaml --max-steps 200 --output ./results/shallow
                        '''
                    }
                    post {
                        always {
                            archiveArtifacts artifacts: 'results/**', allowEmptyArchive: true
                            sh 'docker-compose -f docker-compose.test.yml down -v'
                        }
                    }
                }
            }
        }
        
        stage('Deep Exploration') {
            when {
                anyOf {
                    branch 'main'
                    triggeredBy 'TimerTrigger'
                }
            }
            agent {
                docker { image 'python:3.11' }
            }
            steps {
                sh '''
                    docker-compose -f docker-compose.test.yml up -d
                    sleep 15
                    pip install venomqa
                    venomqa run --config venomqa.yaml --max-steps 2000 --output ./results/deep
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'results/**', allowEmptyArchive: true
                    sh 'docker-compose -f docker-compose.test.yml down -v'
                }
            }
        }
    }
}
```

## Reporting and Notifications

### Combined Report Generation

```python
# scripts/combine_reports.py
import json
from pathlib import Path
from datetime import datetime

def combine_reports():
    results = {
        "timestamp": datetime.now().isoformat(),
        "tests": {}
    }
    
    # Load unit test results
    unit_xml = Path("reports/unit.xml")
    if unit_xml.exists():
        results["tests"]["unit"] = parse_junit_xml(unit_xml)
    
    # Load Schemathesis results
    st_json = Path("schemathesis-report/results.json")
    if st_json.exists():
        results["tests"]["contract"] = json.loads(st_json.read_text())
    
    # Load VenomQA results
    venomqa_json = Path("results/summary.json")
    if venomqa_json.exists():
        results["tests"]["workflow"] = json.loads(venomqa_json.read_text())
    
    # Generate summary
    summary = {
        "total_tests": sum(
            t.get("total", 0) for t in results["tests"].values()
        ),
        "passed": sum(
            t.get("passed", 0) for t in results["tests"].values()
        ),
        "failed": sum(
            t.get("failed", 0) for t in results["tests"].values()
        ),
        "violations": results["tests"]
            .get("workflow", {})
            .get("violations", 0)
    }
    
    results["summary"] = summary
    
    # Write combined report
    Path("combined-report/results.json").write_text(
        json.dumps(results, indent=2)
    )
    
    # Generate HTML summary
    html = generate_html_summary(results)
    Path("combined-report/index.html").write_text(html)
    
    return summary

def generate_html_summary(results):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>API Test Report</title>
        <style>
            body {{ font-family: system-ui; max-width: 800px; margin: 0 auto; padding: 20px; }}
            .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }}
            .card {{ padding: 15px; border-radius: 8px; text-align: center; }}
            .total {{ background: #e3f2fd; }}
            .passed {{ background: #e8f5e9; }}
            .failed {{ background: #ffebee; }}
            .violations {{ background: #fff3e0; }}
            .number {{ font-size: 2em; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>API Test Report</h1>
        <p>Generated: {results['timestamp']}</p>
        
        <div class="summary">
            <div class="card total">
                <div class="number">{results['summary']['total_tests']}</div>
                <div>Total Tests</div>
            </div>
            <div class="card passed">
                <div class="number">{results['summary']['passed']}</div>
                <div>Passed</div>
            </div>
            <div class="card failed">
                <div class="number">{results['summary']['failed']}</div>
                <div>Failed</div>
            </div>
            <div class="card violations">
                <div class="number">{results['summary']['violations']}</div>
                <div>Violations</div>
            </div>
        </div>
    </body>
    </html>
    """

if __name__ == "__main__":
    combine_reports()
```

### Slack Notifications

```yaml
# .github/workflows/api-tests.yml (notification section)
  notify:
    name: Notify Results
    needs: [unit-tests, contract-tests, workflow-tests]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Determine status
        id: status
        run: |
          if [ "${{ needs.workflow-tests.result }}" == "failure" ]; then
            echo "status=failure" >> $GITHUB_OUTPUT
            echo "emoji=:x:" >> $GITHUB_OUTPUT
          else
            echo "status=success" >> $GITHUB_OUTPUT
            echo "emoji=:white_check_mark:" >> $GITHUB_OUTPUT
          fi
      
      - name: Send Slack notification
        uses: slackapi/slack-github-action@v1
        with:
          channel-id: 'api-tests'
          payload: |
            {
              "blocks": [
                {
                  "type": "header",
                  "text": {
                    "type": "plain_text",
                    "text": "${{ steps.status.outputs.emoji }} API Tests: ${{ steps.status.outputs.status }}"
                  }
                },
                {
                  "type": "section",
                  "fields": [
                    {
                      "type": "mrkdwn",
                      "text": "*Repository:*\n${{ github.repository }}"
                    },
                    {
                      "type": "mrkdwn",
                      "text": "*Branch:*\n${{ github.ref_name }}"
                    },
                    {
                      "type": "mrkdwn",
                      "text": "*Commit:*\n${{ github.sha }}"
                    },
                    {
                      "type": "mrkdwn",
                      "text": "*Actor:*\n${{ github.actor }}"
                    }
                  ]
                },
                {
                  "type": "actions",
                  "elements": [
                    {
                      "type": "button",
                      "text": {
                        "type": "plain_text",
                        "text": "View Results"
                      },
                      "url": "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
                    }
                  ]
                }
              ]
            }
        env:
          SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
```

### GitHub PR Comments

```yaml
# .github/workflows/pr-comment.yml
name: PR Test Results

on:
  workflow_run:
    workflows: ["API Tests"]
    types:
      - completed

jobs:
  comment:
    if: github.event.workflow_run.event == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - name: Download artifacts
        uses: actions/github-script@v7
        with:
          script: |
            const artifacts = await github.rest.actions.listWorkflowRunArtifacts({
              owner: context.repo.owner,
              repo: context.repo.repo,
              run_id: context.payload.workflow_run.id,
            });
            
            const matchArtifact = artifacts.data.artifacts.find(
              artifact => artifact.name === 'venomqa-report'
            );
            
            if (matchArtifact) {
              const download = await github.rest.actions.downloadArtifact({
                owner: context.repo.owner,
                repo: context.repo.repo,
                artifact_id: matchArtifact.id,
                archive_format: 'zip',
              });
              
              // Process and create PR comment
              const summary = await processResults(download.data);
              
              await github.rest.issues.createComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: context.payload.workflow_run.pull_requests[0].number,
                body: summary,
              });
            }
```

## Best Practices

### 1. Fast Feedback Loops

```
Commit ──► Unit Tests (< 2 min)
              │
              ├── Pass ──► Contract Tests (< 5 min)
              │                │
              │                ├── Pass ──► PR Approved
              │                │
              │                └── Fail ──► Block PR
              │
              └── Fail ──► Block immediately
```

### 2. Layered Testing Strategy

| Layer | Tests | Speed | Trigger |
|-------|-------|-------|---------|
| L1: Unit | pytest | < 2 min | Every commit |
| L2: Contract | Schemathesis | < 5 min | Every PR |
| L3: Integration | VenomQA shallow | < 15 min | Every PR |
| L4: Deep | VenomQA deep | < 60 min | Main branch, nightly |

### 3. Test Data Management

```python
# tests/conftest.py
import pytest
from venomqa.adapters.postgres import PostgresAdapter

@pytest.fixture(scope="session")
def test_database():
    """Create test database once per session."""
    db = PostgresAdapter(TEST_DATABASE_URL)
    db.connect()
    
    # Seed reference data (products, categories, etc.)
    seed_reference_data(db)
    
    # Create baseline checkpoint
    db.checkpoint("baseline")
    
    yield db
    
    db.close()

@pytest.fixture
def clean_db(test_database):
    """Reset to baseline for each test."""
    test_database.rollback("baseline")
    yield test_database
    test_database.rollback("baseline")
```

### 4. Resource Cleanup

Always clean up Docker resources:

```yaml
# In every workflow
post:
  always:
    - name: Cleanup
      run: docker-compose -f docker-compose.test.yml down -v --remove-orphans
```

## Summary

| CI/CD Platform | Best For | Key Features |
|----------------|----------|--------------|
| **GitHub Actions** | Open source, small teams | Matrix builds, marketplace actions |
| **GitLab CI** | Enterprise, GitLab users | Auto DevOps, built-in container registry |
| **Jenkins** | Complex pipelines, enterprise | Extensive plugins, fine-grained control |

### Recommended Setup

1. **Every commit**: Unit tests + linting
2. **Every PR**: Contract tests + shallow VenomQA exploration
3. **Main branch**: Deep VenomQA exploration + performance tests
4. **Nightly**: Full regression suite with 2000+ steps

---

## Further Reading

- [VenomQA Documentation](https://venomqa.ai)
- [Schemathesis CI Integration](https://schemathesis.readthedocs.io/en/stable/guides/ci.html)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [GitLab CI/CD Documentation](https://docs.gitlab.com/ee/ci/)
- [Jenkins Pipeline Documentation](https://www.jenkins.io/doc/book/pipeline/)

---

*Keywords: CI/CD testing, automated API testing, continuous testing, GitHub Actions, GitLab CI, Jenkins, Docker Compose, API testing automation, test pipeline, CI/CD best practices*
