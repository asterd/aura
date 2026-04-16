#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_ARGS=(-f compose.yaml -f compose.docker.yaml)
CERT_CANDIDATE="${AURA_CA_CERT_FILE:-$ROOT_DIR/nscacert.pem}"
TMP_COMPOSE=""
UP_ARGS=(-d)

cd "$ROOT_DIR"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build)
      UP_ARGS+=(--build)
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
  shift
done

cleanup() {
  if [[ -n "$TMP_COMPOSE" && -f "$TMP_COMPOSE" ]]; then
    rm -f "$TMP_COMPOSE"
  fi
}

trap cleanup EXIT

if [[ -f "$CERT_CANDIDATE" ]]; then
  TMP_COMPOSE="$(mktemp)"
  cat > "$TMP_COMPOSE" <<EOF
services:
  api:
    build:
      secrets:
        - corporate_ca
    environment:
      REQUESTS_CA_BUNDLE: /run/secrets/corporate_ca
      SSL_CERT_FILE: /run/secrets/corporate_ca
    secrets:
      - corporate_ca

  worker:
    build:
      secrets:
        - corporate_ca
    environment:
      REQUESTS_CA_BUNDLE: /run/secrets/corporate_ca
      SSL_CERT_FILE: /run/secrets/corporate_ca
    secrets:
      - corporate_ca

  web:
    build:
      secrets:
        - corporate_ca
    environment:
      NODE_EXTRA_CA_CERTS: /run/secrets/corporate_ca
    secrets:
      - corporate_ca

secrets:
  corporate_ca:
    file: "$CERT_CANDIDATE"
EOF
  COMPOSE_ARGS+=(-f "$TMP_COMPOSE")
  echo "Using optional corporate CA certificate: $CERT_CANDIDATE"
fi

docker compose "${COMPOSE_ARGS[@]}" up "${UP_ARGS[@]}"

cat <<'EOF'

Stack avviato.

Frontend: http://localhost:3000
Login:    http://localhost:3000/login
API:      http://localhost:8000
Docs:     http://localhost:8000/docs
Health:   http://localhost:8000/api/v1/health

Per seguire i log:
docker compose -f compose.yaml -f compose.docker.yaml logs -f
EOF
