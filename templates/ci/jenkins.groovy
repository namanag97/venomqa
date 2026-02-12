#!/usr/bin/env groovy

pipeline {
    agent {
        kubernetes {
            yaml '''
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: python
    image: python:3.12-slim
    command:
    - cat
    tty: true
    resources:
      limits:
        memory: "2Gi"
        cpu: "1"
      requests:
        memory: "1Gi"
        cpu: "500m"
  - name: docker
    image: docker:24.0-dind
    securityContext:
      privileged: true
    volumeMounts:
    - name: docker-sock
      mountPath: /var/run/docker.sock
  volumes:
  - name: docker-sock
    hostPath:
      path: /var/run/docker.sock
'''
        }
    }
    
    environment {
        VENOMQA_REPORT_DIR = 'reports'
        PYTHON_VERSION = '3.12'
    }
    
    options {
        timeout(time: 1, unit: 'HOURS')
        buildDiscarder(logRotator(numToKeepStr: '20'))
        ansiColor('xterm')
        timestamps()
        disableConcurrentBuilds()
        retry(2)
    }
    
    parameters {
        choice(
            name: 'ENVIRONMENT',
            choices: ['staging', 'production', 'development'],
            description: 'Target environment for tests'
        )
        string(
            name: 'TEST_TAGS',
            defaultValue: '',
            description: 'Comma-separated test tags to run'
        )
        booleanParam(
            name: 'RUN_PERFORMANCE',
            defaultValue: false,
            description: 'Run performance tests'
        )
        booleanParam(
            name: 'SKIP_E2E',
            defaultValue: false,
            description: 'Skip E2E tests'
        )
    }
    
    stages {
        stage('Setup') {
            steps {
                container('python') {
                    sh '''
                        python -m venv .venv
                        . .venv/bin/activate
                        pip install --upgrade pip
                        pip install -e ".[dev]"
                    '''
                }
            }
        }
        
        stage('Lint') {
            steps {
                container('python') {
                    sh '''
                        . .venv/bin/activate
                        pip install ruff mypy
                        ruff check . --output-format=junit > reports/lint-junit.xml || true
                        mypy . --ignore-missing-imports --junit-xml reports/mypy-junit.xml || true
                    '''
                }
            }
            post {
                always {
                    junit 'reports/*-junit.xml'
                }
            }
        }
        
        stage('Unit Tests') {
            steps {
                container('python') {
                    sh '''
                        . .venv/bin/activate
                        pytest tests/unit \
                            -v \
                            --junitxml=reports/unit-junit.xml \
                            --cov=venomqa \
                            --cov-report=xml:reports/coverage.xml \
                            --cov-report=html:reports/coverage-html
                    '''
                }
            }
            post {
                always {
                    junit 'reports/unit-junit.xml'
                    publishHTML([
                        allowMissing: true,
                        alwaysLinkToLastBuild: true,
                        keepAll: true,
                        reportDir: 'reports/coverage-html',
                        reportFiles: 'index.html',
                        reportName: 'Coverage Report'
                    ])
                }
            }
        }
        
        stage('API Integration Tests') {
            environment {
                API_BASE_URL = 'http://localhost:8000'
                DATABASE_URL = credentials('venomqa-database-url')
                REDIS_URL = 'redis://localhost:6379/0'
            }
            steps {
                container('python') {
                    sh '''
                        . .venv/bin/activate
                        
                        # Start mock API server in background
                        python -m http.server 8000 --directory tests/fixtures/mock_api &
                        MOCK_PID=$!
                        sleep 5
                        
                        # Run VenomQA
                        venomqa run \
                            --config venomqa.yaml \
                            --output-dir ${VENOMQA_REPORT_DIR} \
                            --format html json junit \
                            --parallel 4 \
                            ${TEST_TAGS ? "--tags " + TEST_TAGS : ""}
                        
                        kill $MOCK_PID || true
                    '''
                }
            }
            post {
                always {
                    junit 'reports/*-junit.xml'
                    archiveArtifacts artifacts: 'reports/*.html, reports/*.json', allowEmptyArchive: true
                }
            }
        }
        
        stage('E2E Tests') {
            when {
                expression { 
                    return params.SKIP_E2E == false && 
                           (env.BRANCH_NAME == 'main' || env.BRANCH_NAME == 'develop')
                }
            }
            steps {
                container('docker') {
                    sh '''
                        docker-compose -f docker-compose.qa.yml up -d
                        
                        # Wait for services
                        for i in $(seq 1 60); do
                            if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
                                echo "API is ready"
                                break
                            fi
                            echo "Waiting for API... ($i/60)"
                            sleep 5
                        done
                    '''
                }
                container('python') {
                    sh '''
                        . .venv/bin/activate
                        venomqa run \
                            --config venomqa.yaml \
                            --journeys-dir journeys \
                            --output-dir ${VENOMQA_REPORT_DIR} \
                            --format html json junit sarif \
                            --tags e2e \
                            --parallel 2
                    '''
                }
            }
            post {
                always {
                    container('docker') {
                        sh 'docker-compose -f docker-compose.qa.yml down -v || true'
                    }
                    junit 'reports/*-junit.xml'
                    archiveArtifacts artifacts: 'reports/', allowEmptyArchive: true
                }
            }
        }
        
        stage('Performance Tests') {
            when {
                expression { 
                    return params.RUN_PERFORMANCE || env.BRANCH_NAME == 'main'
                }
            }
            environment {
                PERF_API_URL = credentials('perf-api-url')
            }
            steps {
                container('python') {
                    sh '''
                        . .venv/bin/activate
                        pip install -e ".[dev,performance]"
                        
                        venomqa run \
                            --config venomqa.yaml \
                            --journeys-dir journeys \
                            --output-dir ${VENOMQA_REPORT_DIR} \
                            --tags performance \
                            --parallel 8 \
                            --iterations 100
                    '''
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: 'reports/', allowEmptyArchive: true
                }
            }
        }
        
        stage('Security Scan') {
            steps {
                container('python') {
                    sh '''
                        . .venv/bin/activate
                        pip install bandit safety
                        
                        bandit -r venomqa -f xml -o reports/bandit.xml || true
                        safety check --json > reports/safety.json || true
                    '''
                }
            }
            post {
                always {
                    recordIssues(tools: [xmlPattern('reports/bandit.xml')])
                }
            }
        }
    }
    
    post {
        always {
            archiveArtifacts artifacts: 'reports/', allowEmptyArchive: true
            cleanWs()
        }
        success {
            echo 'VenomQA pipeline completed successfully!'
        }
        failure {
            mail(
                to: "${env.CHANGE_AUTHOR_EMAIL ?: 'team@example.com'}",
                subject: "VenomQA Pipeline Failed: ${env.JOB_NAME} #${env.BUILD_NUMBER}",
                body: """
                    Pipeline failed!
                    
                    Job: ${env.JOB_NAME}
                    Build: #${env.BUILD_NUMBER}
                    URL: ${env.BUILD_URL}
                    Branch: ${env.BRANCH_NAME}
                    Commit: ${env.GIT_COMMIT}
                """
            )
        }
    }
}
