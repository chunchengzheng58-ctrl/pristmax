#!/bin/bash
set -e

echo "Starting Pristmax Storage..."

# Create necessary directories
mkdir -p /app/data /app/logs /app/config /app/storage

# Set permissions
chmod -R 755 /app

# Check if first run
if [ ! -f /app/config/app.yaml ]; then
    echo "First run detected, creating default configuration..."
    cat > /app/config/app.yaml << 'EOF'
app_name: Pristmax
version: 1.0.0
debug: false
host: "0.0.0.0"
port: 5001

storage:
  default_path: /app/storage
  max_file_size_mb: 10240
  supported_formats:
    - .mp4
    - .avi
    - .mkv
    - .mov

dedup:
  enabled: true
  min_chunk_size: 2048
  max_chunk_size: 16384

monitoring:
  enabled: true
  port: 9090
EOF
fi

echo "Configuration loaded"
echo "Starting API server on port $PRISTMAX_PORT..."

# Start the application
exec python -m api.server
