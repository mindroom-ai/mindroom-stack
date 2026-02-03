#!/bin/bash
# Entrypoint script for Synapse container

# Ensure proper ownership of data directories
echo "Setting permissions for UID ${UID:-1000} and GID ${GID:-1000}..."
chown -R ${UID:-1000}:${GID:-1000} /data
# Ensure media_store directory exists with correct permissions
mkdir -p /data/media_store
chown -R ${UID:-1000}:${GID:-1000} /data/media_store
chmod -R 755 /data/media_store

# Generate signing key if it doesn't exist
if [ ! -f "/data/signing.key" ]; then
    echo "No signing key found. Generating one..."
    python -m synapse.crypto.signing_key -o /data/signing.key
    echo "Signing key generated."
fi

# Wait for dependencies to be reachable
wait_for_service() {
    local host="$1"
    local port="$2"
    local retries=60
    local count=0

    echo "Waiting for $host:$port..."
    while ! (echo > "/dev/tcp/$host/$port") >/dev/null 2>&1; do
        count=$((count + 1))
        if [ "$count" -ge "$retries" ]; then
            echo "Timed out waiting for $host:$port"
            return 1
        fi
        sleep 1
    done
    echo "$host:$port is available"
}

wait_for_service postgres 5432
wait_for_service redis 6379

# Execute the original Synapse entrypoint
exec /start.py
