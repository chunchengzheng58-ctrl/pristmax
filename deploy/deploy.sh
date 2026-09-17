#!/bin/bash
# -*- coding: utf-8 -*-
"""
Deployment Script

Build and deploy the Semantic Data Reduction System.
"""

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="semantic-reduction"
IMAGE_TAG="${1:-latest}"
REGISTRY="${2:-}"

echo "=========================================="
echo "Semantic Data Reduction System Deployment"
echo "=========================================="

# Build Docker image
echo -e "${YELLOW}[1/4] Building Docker image...${NC}"
docker build -t ${IMAGE_NAME}:${IMAGE_TAG} .

if [ -n "$REGISTRY" ]; then
    echo -e "${YELLOW}[2/4] Tagging for registry: $REGISTRY${NC}"
    docker tag ${IMAGE_NAME}:${IMAGE_TAG} ${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}
    echo -e "${YELLOW}[3/4] Pushing to registry...${NC}"
    docker push ${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}
else
    echo -e "${YELLOW}[2/4] Skipping registry push (no registry specified)${NC}"
    echo -e "${YELLOW}[3/4] Skipping registry push${NC}"
fi

# Docker Compose deployment
echo -e "${YELLOW}[4/4] Starting services with Docker Compose...${NC}"
docker-compose up -d

echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""
echo "Services:"
echo "  - API Server: http://localhost:5000"
echo "  - MinIO Console: http://localhost:9001 (optional)"
echo "  - PostgreSQL: localhost:5432 (optional)"
echo ""
echo "Useful commands:"
echo "  - View logs: docker-compose logs -f api"
echo "  - Stop services: docker-compose down"
echo "  - Restart: docker-compose restart"
echo ""
