#!/bin/bash
#
# Wrapper script to blacklist all currently online Willhaben listings
#
# This script runs the blacklist_online_listings.py script inside the Docker container
# to ensure all dependencies are available.
#
# Usage:
#   ./blacklist-online.sh [--dry-run]
#
# Options:
#   --dry-run    Show what would be blacklisted without actually doing it
#

set -e

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "Error: docker-compose is not installed or not in PATH"
    exit 1
fi

# Check if the docker-compose.yaml exists
if [ ! -f "docker-compose.yaml" ]; then
    echo "Error: docker-compose.yaml not found. Please run this script from the Flatjaga directory."
    exit 1
fi

echo "============================================================"
echo "Blacklist Online Listings Tool"
echo "============================================================"
echo ""

# Check if container is running
if docker-compose ps | grep -q "Up"; then
    echo "Using existing running container..."
    docker-compose exec app python blacklist_online_listings.py "$@"
else
    echo "Starting temporary container..."
    echo ""
    docker-compose run --rm app python blacklist_online_listings.py "$@"
fi
