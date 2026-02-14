# CI/CD Integration

Learn how to integrate VenomQA into your continuous integration and deployment pipelines.

**Time:** 10 minutes

**What you'll learn:**

- Running VenomQA in GitHub Actions
- Generating JUnit XML reports
- Uploading test artifacts
- Configuring other CI/CD systems

## GitHub Actions

### Basic Setup

Create `.github/workflows/qa-tests.yml`:

```yaml
name: QA Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: |
          pip install venomqa
          pip install -r requirements.txt  # Your app dependencies

      - name: Run QA tests
        run: venomqa run

      - name: Generate JUnit report
        if: always()
        run: venomqa report --format junit --output reports/junit.xml

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: qa-reports
          path: reports/

      - name: Publish test results
        if: always()
        uses: dorny/test-reporter@v1
        with:
          name: QA Tests
          path: reports/junit.xml
          reporter: java-junit
```

### With PostgreSQL Service

```yaml
name: QA Tests with Database

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: qa_test
          POSTGRES_USER: qa
          POSTGRES_PASSWORD: secret
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      api:
        image: your-api:latest
        env:
          DATABASE_URL: postgresql://qa:secret@postgres:5432/qa_test
        ports:
          - 8000:8000

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install VenomQA
        run: pip install "venomqa[postgres]"

      - name: Run QA tests
        env:
          VENOMQA_BASE_URL: http://localhost:8000
          VENOMQA_DB_URL: postgresql://qa:secret@localhost:5432/qa_test
        run: venomqa run --no-infra

      - name: Generate reports
        if: always()
        run: |
          venomqa report --format junit --output reports/junit.xml
          venomqa report --format html --output reports/test.html

      - name: Upload artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: qa-reports
          path: reports/
```

### Matrix Testing

Test across multiple Python versions:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install and test
        run: |
          pip install venomqa
          venomqa run
```

## GitLab CI

Create `.gitlab-ci.yml`:

```yaml
stages:
  - test

variables:
  POSTGRES_DB: qa_test
  POSTGRES_USER: qa
  POSTGRES_PASSWORD: secret

qa-tests:
  stage: test
  image: python:3.11

  services:
    - name: postgres:15
      alias: postgres

  variables:
    VENOMQA_BASE_URL: http://api:8000
    VENOMQA_DB_URL: postgresql://qa:secret@postgres:5432/qa_test

  before_script:
    - pip install "venomqa[postgres]"

  script:
    - venomqa run --no-infra

  after_script:
    - venomqa report --format junit --output reports/junit.xml

  artifacts:
    when: always
    paths:
      - reports/
    reports:
      junit: reports/junit.xml
```

## CircleCI

Create `.circleci/config.yml`:

```yaml
version: 2.1

jobs:
  qa-tests:
    docker:
      - image: python:3.11
      - image: postgres:15
        environment:
          POSTGRES_DB: qa_test
          POSTGRES_USER: qa
          POSTGRES_PASSWORD: secret

    environment:
      VENOMQA_BASE_URL: http://localhost:8000
      VENOMQA_DB_URL: postgresql://qa:secret@localhost:5432/qa_test

    steps:
      - checkout

      - run:
          name: Install dependencies
          command: pip install "venomqa[postgres]"

      - run:
          name: Run QA tests
          command: venomqa run --no-infra

      - run:
          name: Generate reports
          when: always
          command: |
            venomqa report --format junit --output reports/junit.xml
            venomqa report --format html --output reports/test.html

      - store_test_results:
          path: reports

      - store_artifacts:
          path: reports

workflows:
  version: 2
  test:
    jobs:
      - qa-tests
```

## Jenkins Pipeline

Create `Jenkinsfile`:

```groovy
pipeline {
    agent any

    environment {
        VENOMQA_BASE_URL = 'http://localhost:8000'
        VENOMQA_DB_URL = credentials('qa-database-url')
    }

    stages {
        stage('Setup') {
            steps {
                sh 'pip install "venomqa[postgres]"'
            }
        }

        stage('Start Services') {
            steps {
                sh 'docker compose -f docker-compose.qa.yml up -d'
                sh 'sleep 10'  // Wait for services
            }
        }

        stage('Run Tests') {
            steps {
                sh 'venomqa run --no-infra'
            }
        }

        stage('Generate Reports') {
            steps {
                sh '''
                    venomqa report --format junit --output reports/junit.xml
                    venomqa report --format html --output reports/test.html
                '''
            }
        }
    }

    post {
        always {
            sh 'docker compose -f docker-compose.qa.yml down'

            junit 'reports/junit.xml'

            publishHTML(target: [
                allowMissing: false,
                alwaysLinkToLastBuild: true,
                keepAll: true,
                reportDir: 'reports',
                reportFiles: 'test.html',
                reportName: 'QA Report'
            ])
        }
    }
}
```

## Azure DevOps

Create `azure-pipelines.yml`:

```yaml
trigger:
  - main
  - develop

pool:
  vmImage: 'ubuntu-latest'

services:
  postgres:
    image: postgres:15
    ports:
      - 5432:5432
    env:
      POSTGRES_DB: qa_test
      POSTGRES_USER: qa
      POSTGRES_PASSWORD: secret

variables:
  VENOMQA_BASE_URL: http://localhost:8000
  VENOMQA_DB_URL: postgresql://qa:secret@localhost:5432/qa_test

steps:
  - task: UsePythonVersion@0
    inputs:
      versionSpec: '3.11'

  - script: pip install "venomqa[postgres]"
    displayName: 'Install VenomQA'

  - script: venomqa run --no-infra
    displayName: 'Run QA Tests'

  - script: |
      venomqa report --format junit --output $(Build.ArtifactStagingDirectory)/junit.xml
    displayName: 'Generate Report'
    condition: always()

  - task: PublishTestResults@2
    inputs:
      testResultsFormat: 'JUnit'
      testResultsFiles: '$(Build.ArtifactStagingDirectory)/junit.xml'
    condition: always()
```

## Report Formats

VenomQA supports multiple report formats for CI/CD:

| Format | Use Case | Command |
|--------|----------|---------|
| JUnit XML | CI/CD test results | `--format junit` |
| HTML | Human-readable | `--format html` |
| JSON | Custom processing | `--format json` |
| Markdown | PR comments | `--format markdown` |
| SARIF | Security tools | `--format sarif` |

### Generating Multiple Reports

```bash
venomqa report --format junit --output reports/junit.xml
venomqa report --format html --output reports/test.html
venomqa report --format markdown --output reports/summary.md
```

## Environment Variables

Configure VenomQA via environment variables in CI/CD:

```bash
# Required
export VENOMQA_BASE_URL="http://api:8000"

# Database (optional)
export VENOMQA_DB_URL="postgresql://user:pass@host:5432/db"
export VENOMQA_DB_BACKEND="postgresql"

# Execution
export VENOMQA_TIMEOUT=60
export VENOMQA_FAIL_FAST=true
export VENOMQA_PARALLEL_PATHS=1

# Debugging
export VENOMQA_VERBOSE=true
```

## Best Practices

### 1. Use `--no-infra` in CI

When services are provided by CI, skip Docker management:

```bash
venomqa run --no-infra
```

### 2. Always Generate Reports

Use `if: always()` (GitHub) or `when: always` (GitLab):

```yaml
- name: Generate report
  if: always()  # Run even if tests fail
  run: venomqa report --format junit --output reports/junit.xml
```

### 3. Upload Artifacts

Always upload reports for debugging:

```yaml
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: qa-reports
    path: reports/
```

### 4. Use Secrets for Credentials

Never hardcode credentials:

```yaml
# GitHub Actions
env:
  VENOMQA_DB_URL: ${{ secrets.QA_DATABASE_URL }}

# GitLab CI
variables:
  VENOMQA_DB_URL: $CI_QA_DATABASE_URL
```

### 5. Fail Fast in PRs

For pull requests, fail fast to get quick feedback:

```yaml
- name: Run tests
  run: venomqa run --fail-fast
```

## Troubleshooting

### Tests timeout in CI

Increase timeout for CI environments:

```yaml
env:
  VENOMQA_TIMEOUT: 120  # 2 minutes
```

### Database connection fails

Ensure service is ready:

```yaml
services:
  postgres:
    options: >-
      --health-cmd pg_isready
      --health-interval 10s
      --health-timeout 5s
      --health-retries 5
```

### "Journey not found"

Ensure journeys directory is included:

```yaml
- uses: actions/checkout@v4  # Includes all files
```

## Next Steps

- [Configuration](../getting-started/configuration.md) - All configuration options
- [CLI Reference](../reference/cli.md) - Complete CLI documentation
- [Examples](../examples/index.md) - More CI/CD examples
