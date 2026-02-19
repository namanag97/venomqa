# CI/CD Integration

Run VenomQA in your continuous integration pipeline.

## Overview

VenomQA fits naturally into CI/CD workflows:

```yaml
# Typical CI pipeline
jobs:
  unit-tests:      # Fast feedback
  schema-tests:    # Schemathesis
  sequence-tests:  # VenomQA ← You are here
  deploy:          # Only if all pass
```

## GitHub Actions

### Basic Setup

Create `.github/workflows/venomqa.yml`:

```yaml
name: VenomQA Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  sequence-tests:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: testdb
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      
      api:
        image: your-api:latest
        ports:
          - 8000:8000
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
          pip install psycopg[binary]
      
      - name: Run VenomQA
        env:
          API_URL: http://localhost:8000
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/testdb
        run: |
          venomqa run qa/ --report html
      
      - name: Upload Report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: venomqa-report
          path: reports/
```

### With PR Comments

```yaml
      - name: Comment on PR
        if: github.event_name == 'pull_request' && failure()
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const report = fs.readFileSync('reports/summary.txt', 'utf8');
            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `## VenomQA Results\n\n\`\`\`\n${report}\n\`\`\``
            });
```

### Matrix Testing

```yaml
jobs:
  sequence-tests:
    strategy:
      matrix:
        python-version: ['3.10', '3.11', '3.12']
        database: ['postgres:14', 'postgres:15']
    
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: ${{ matrix.database }}
        # ...
    
    steps:
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      # ...
```

## GitLab CI

### Basic Setup

Create `.gitlab-ci.yml`:

```yaml
stages:
  - test
  - report

venomqa:
  stage: test
  image: python:3.11
  
  services:
    - name: postgres:15
      alias: db
    - name: your-api:latest
      alias: api
  
  variables:
    POSTGRES_PASSWORD: postgres
    POSTGRES_DB: testdb
    API_URL: http://api:8000
    DATABASE_URL: postgresql://postgres:postgres@db:5432/testdb
  
  before_script:
    - pip install -e ".[dev]"
    - pip install psycopg[binary]
  
  script:
    - venomqa run qa/ --report html --output reports/
  
  artifacts:
    when: always
    paths:
      - reports/
    expire_in: 1 week
  
  coverage: '/States visited: (\d+)/'
```

### With Review App

```yaml
review:
  stage: deploy
  script:
    - deploy_to_review_app
  environment:
    name: review/$CI_COMMIT_REF_NAME
    url: https://review-$CI_COMMIT_REF_SLUG.example.com
    on_stop: stop_review

venomqa-on-review:
  stage: test
  needs: [review]
  script:
    - export API_URL=$REVIEW_APP_URL
    - venomqa run qa/
```

## Jenkins

### Jenkinsfile

```groovy
pipeline {
  agent any
  
  stages {
    stage('Setup') {
      steps {
        sh 'pip install -e ".[dev]"'
        sh 'pip install psycopg[binary]'
      }
    }
    
    stage('Start Services') {
      steps {
        sh 'docker-compose -f docker-compose.test.yml up -d'
        sh 'sleep 10'  // Wait for services
      }
    }
    
    stage('VenomQA') {
      steps {
        withCredentials([
          string(credentialsId: 'api-token', variable: 'API_TOKEN'),
          string(credentialsId: 'db-url', variable: 'DATABASE_URL')
        ]) {
          sh '''
            export API_URL=http://localhost:8000
            venomqa run qa/ --report html --output reports/
          '''
        }
      }
      
      post {
        always {
          archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true
          publishHTML(target: [
            allowMissing: true,
            alwaysLinkToLastBuild: true,
            keepAll: true,
            reportDir: 'reports',
            reportFiles: 'trace.html',
            reportName: 'VenomQA Report'
          ])
        }
      }
    }
  }
  
  post {
    always {
      sh 'docker-compose -f docker-compose.test.yml down'
    }
  }
}
```

## CircleCI

### .circleci/config.yml

```yaml
version: 2.1

jobs:
  venomqa:
    docker:
      - image: python:3.11
      - image: postgres:15
        environment:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: testdb
      - image: your-api:latest
    
    environment:
      API_URL: http://localhost:8000
      DATABASE_URL: postgresql://postgres:postgres@localhost:5432/testdb
    
    steps:
      - checkout
      
      - run:
          name: Install dependencies
          command: |
            pip install -e ".[dev]"
            pip install psycopg[binary]
      
      - run:
          name: Run VenomQA
          command: venomqa run qa/ --report html
      
      - store_artifacts:
          path: reports/
          destination: venomqa-report
      
      - store_test_results:
          path: reports/junit.xml

workflows:
  version: 2
  test:
    jobs:
      - venomqa
```

## Docker Compose for CI

Create `docker-compose.test.yml`:

```yaml
version: '3.8'

services:
  api:
    build: ./app
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://postgres:postgres@db:5432/testdb
    depends_on:
      - db
  
  db:
    image: postgres:15
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: testdb
    ports:
      - "5432:5432"
  
  venomqa:
    build:
      context: .
      dockerfile: Dockerfile.venomqa
    environment:
      API_URL: http://api:8000
      DATABASE_URL: postgresql://postgres:postgres@db:5432/testdb
    depends_on:
      - api
      - db
    volumes:
      - ./reports:/app/reports

# Dockerfile.venomqa
FROM python:3.11
WORKDIR /app
COPY . .
RUN pip install -e ".[dev]" && pip install psycopg[binary]
CMD ["venomqa", "run", "qa/", "--report", "html", "--output", "/app/reports/"]
```

## Best Practices

### 1. Use Service Containers

```yaml
# Good: Isolated services
services:
  postgres:
    image: postgres:15
  api:
    image: your-api:latest

# Bad: External dependencies
# Can't guarantee availability
```

### 2. Upload Artifacts

```yaml
# Always upload reports, even on failure
artifacts:
  when: always
  paths:
    - reports/
```

### 3. Set Timeouts

```yaml
# Prevent hung tests
script:
  - timeout 30m venomqa run qa/
```

### 4. Fail Fast in PRs

```yaml
# Quick feedback for developers
venomqa:
  script:
    - venomqa run qa/ --max-steps 100 --fail-fast
```

### 5. Thorough in Main

```yaml
# Full exploration for main branch
venomqa-main:
  if: github.ref == 'refs/heads/main'
  script:
    - venomqa run qa/ --max-steps 500
```

## Next Steps

- [Reporting](../reference/reporters.md) - Report formats
- [Configuration](../getting-started/configuration.md) - Environment setup
- [Examples](../examples/index.md) - Real-world setups
