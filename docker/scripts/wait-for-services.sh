#!/bin/bash
#
# Wait for services to be ready before running VenomQA
#
# Usage:
#   wait-for-services.sh [options] -- venomqa run ...
#
# Options:
#   --postgres HOST:PORT    Wait for PostgreSQL
#   --redis HOST:PORT       Wait for Redis
#   --mysql HOST:PORT       Wait for MySQL
#   --http URL              Wait for HTTP endpoint
#   --timeout SECONDS       Maximum wait time (default: 60)
#
# Example:
#   wait-for-services.sh --postgres localhost:5432 --redis localhost:6379 -- venomqa run

set -e

TIMEOUT=${WAIT_TIMEOUT:-60}
POSTGRES_TARGETS=()
REDIS_TARGETS=()
MYSQL_TARGETS=()
HTTP_TARGETS=()
COMMAND=()

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --postgres)
            POSTGRES_TARGETS+=("$2")
            shift 2
            ;;
        --redis)
            REDIS_TARGETS+=("$2")
            shift 2
            ;;
        --mysql)
            MYSQL_TARGETS+=("$2")
            shift 2
            ;;
        --http)
            HTTP_TARGETS+=("$2")
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --)
            shift
            COMMAND=("$@")
            break
            ;;
        *)
            COMMAND+=("$1")
            shift
            ;;
    esac
done

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

wait_for_postgres() {
    local target=$1
    local host=$(echo "$target" | cut -d: -f1)
    local port=$(echo "$target" | cut -d: -f2)
    port=${port:-5432}

    log "Waiting for PostgreSQL at $host:$port..."

    local start=$(date +%s)
    while ! pg_isready -h "$host" -p "$port" -q 2>/dev/null; do
        local now=$(date +%s)
        if [ $((now - start)) -ge $TIMEOUT ]; then
            log "ERROR: PostgreSQL at $host:$port did not become ready within ${TIMEOUT}s"
            return 1
        fi
        sleep 1
    done

    log "PostgreSQL at $host:$port is ready"
}

wait_for_redis() {
    local target=$1
    local host=$(echo "$target" | cut -d: -f1)
    local port=$(echo "$target" | cut -d: -f2)
    port=${port:-6379}

    log "Waiting for Redis at $host:$port..."

    local start=$(date +%s)
    while ! redis-cli -h "$host" -p "$port" ping 2>/dev/null | grep -q PONG; do
        local now=$(date +%s)
        if [ $((now - start)) -ge $TIMEOUT ]; then
            log "ERROR: Redis at $host:$port did not become ready within ${TIMEOUT}s"
            return 1
        fi
        sleep 1
    done

    log "Redis at $host:$port is ready"
}

wait_for_mysql() {
    local target=$1
    local host=$(echo "$target" | cut -d: -f1)
    local port=$(echo "$target" | cut -d: -f2)
    port=${port:-3306}

    log "Waiting for MySQL at $host:$port..."

    local start=$(date +%s)
    while ! mysqladmin ping -h "$host" -P "$port" --silent 2>/dev/null; do
        local now=$(date +%s)
        if [ $((now - start)) -ge $TIMEOUT ]; then
            log "ERROR: MySQL at $host:$port did not become ready within ${TIMEOUT}s"
            return 1
        fi
        sleep 1
    done

    log "MySQL at $host:$port is ready"
}

wait_for_http() {
    local url=$1

    log "Waiting for HTTP endpoint at $url..."

    local start=$(date +%s)
    while ! curl -sf "$url" > /dev/null 2>&1; do
        local now=$(date +%s)
        if [ $((now - start)) -ge $TIMEOUT ]; then
            log "ERROR: HTTP endpoint at $url did not become ready within ${TIMEOUT}s"
            return 1
        fi
        sleep 1
    done

    log "HTTP endpoint at $url is ready"
}

# Wait for all services
for target in "${POSTGRES_TARGETS[@]}"; do
    wait_for_postgres "$target" || exit 1
done

for target in "${REDIS_TARGETS[@]}"; do
    wait_for_redis "$target" || exit 1
done

for target in "${MYSQL_TARGETS[@]}"; do
    wait_for_mysql "$target" || exit 1
done

for target in "${HTTP_TARGETS[@]}"; do
    wait_for_http "$target" || exit 1
done

log "All services are ready"

# Execute command if provided
if [ ${#COMMAND[@]} -gt 0 ]; then
    log "Executing: ${COMMAND[*]}"
    exec "${COMMAND[@]}"
fi
