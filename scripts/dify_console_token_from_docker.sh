#!/usr/bin/env bash
# Generate short-lived Dify Console API tokens from a local self-hosted Dify
# Docker Compose stack. The output is an env file that can be sourced by the
# r1-r4 runner; it intentionally avoids printing token values to stderr.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${SCRIPT_DIR}/.." && pwd)"

COMPOSE_FILE="${DIFY_DOCKER_COMPOSE:-${REPO}/../dify_rag/dify/docker/docker-compose.yaml}"
ACCOUNT_ID="${DIFY_CONSOLE_ACCOUNT_ID:-}"
OUT=""
TTL_SECONDS="${DIFY_CONSOLE_TOKEN_TTL_SECONDS:-7200}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --compose-file)
      COMPOSE_FILE="$2"
      shift
      ;;
    --account-id)
      ACCOUNT_ID="$2"
      shift
      ;;
    --out)
      OUT="$2"
      shift
      ;;
    --ttl-seconds)
      TTL_SECONDS="$2"
      shift
      ;;
    --help|-h)
      sed -n '1,24p' "$0"
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      exit 2
      ;;
  esac
  shift
done

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "ERROR: Dify docker compose file not found: ${COMPOSE_FILE}" >&2
  exit 1
fi

compose() {
  docker compose -f "${COMPOSE_FILE}" "$@"
}

if [[ -z "${ACCOUNT_ID}" ]]; then
  ACCOUNT_ID="$(
    compose exec -T db_postgres psql -U postgres -d dify -Atc \
      "select id from accounts where status = 'active' order by last_login_at desc nulls last, created_at desc limit 1;" \
      | tr -d '[:space:]'
  )"
fi

if [[ -z "${ACCOUNT_ID}" ]]; then
  echo "ERROR: could not resolve a Dify console account id" >&2
  exit 1
fi

TOKEN_ENV="$(
  compose exec -T \
    -e TOKEN_ACCOUNT_ID="${ACCOUNT_ID}" \
    -e TOKEN_TTL_SECONDS="${TTL_SECONDS}" \
    api python -c '
import os
import time
import jwt

uid = os.environ["TOKEN_ACCOUNT_ID"]
ttl = int(os.environ.get("TOKEN_TTL_SECONDS", "7200"))
exp = int(time.time()) + ttl
secret = os.environ["SECRET_KEY"]
issuer = os.environ.get("EDITION", "SELF_HOSTED")

access = jwt.encode(
    {"user_id": uid, "exp": exp, "iss": issuer, "sub": "Console API Passport"},
    secret,
    algorithm="HS256",
)
csrf = jwt.encode({"exp": exp, "sub": uid}, secret, algorithm="HS256")

print(f"export DIFY_CONSOLE_ACCESS_TOKEN={access!r}")
print(f"export DIFY_CONSOLE_CSRF_TOKEN={csrf!r}")
'
)"

if [[ -n "${OUT}" ]]; then
  mkdir -p "$(dirname "${OUT}")"
  umask 077
  printf '%s\n' "${TOKEN_ENV}" > "${OUT}"
  chmod 600 "${OUT}"
  echo "wrote Dify console token env: ${OUT}" >&2
else
  printf '%s\n' "${TOKEN_ENV}"
fi
