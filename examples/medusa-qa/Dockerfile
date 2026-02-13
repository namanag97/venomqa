FROM node:20-alpine

# Install system dependencies
RUN apk add --no-cache \
    python3 \
    make \
    g++ \
    wget \
    bash

# Create app directory
WORKDIR /app

# Install Medusa CLI globally
RUN npm install -g @medusajs/medusa-cli

# Create a new Medusa project
RUN medusa new . --skip-db --skip-env

# Install dependencies
RUN npm install

# Copy custom configuration if needed
# COPY medusa-config.js /app/

# Expose ports
# 9000 for backend
# 7001 for admin dashboard
EXPOSE 9000 7001

# Create startup script
RUN echo '#!/bin/sh' > /app/start.sh && \
    echo 'medusa migrations run' >> /app/start.sh && \
    echo 'medusa user -e admin@test.com -p supersecret 2>/dev/null || echo "Admin user already exists"' >> /app/start.sh && \
    echo 'medusa develop' >> /app/start.sh && \
    chmod +x /app/start.sh

CMD ["/app/start.sh"]
