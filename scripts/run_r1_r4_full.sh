#!/usr/bin/env bash
# New rag_evaluation_master.csv に対して r1-r4 を一気通貫で再生成する。
#
# 手動作業が必要な箇所:
#   - VLM/embedding 用モデルのロード確認
#   - r1/r2 生成前の openai/gpt-oss-20b ロード
#   - r1/r2 Judge および r3/r4 用 qwen/qwen3.6-35b-a3b への切替
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${SCRIPT_DIR}/.." && pwd)"

RUN_ID=""
RUN_SLUG=""
SKIP_DOWNLOAD=0
SKIP_INGEST=0
SKIP_APPS=0
ASSUME_YES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id)
      RUN_ID="$2"
      shift
      ;;
    --run-slug)
      RUN_SLUG="$2"
      shift
      ;;
    --skip-download) SKIP_DOWNLOAD=1 ;;
    --skip-ingest) SKIP_INGEST=1 ;;
    --skip-apps) SKIP_APPS=1 ;;
    --yes) ASSUME_YES=1 ;;
    --help|-h)
      sed -n '1,32p' "$0"
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      exit 2
      ;;
  esac
  shift
done

cd "${REPO}"
if [[ -x "${REPO}/.venv/bin/python3" ]]; then
  export PATH="${REPO}/.venv/bin:${PATH}"
elif [[ -x "${REPO}/.venv/bin/python" ]]; then
  export PATH="${REPO}/.venv/bin:${PATH}"
fi

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ ! -f rag_evaluation_master.csv ]]; then
  echo "ERROR: rag_evaluation_master.csv がありません。" >&2
  exit 1
fi

MASTER_SHA="$(shasum -a 256 rag_evaluation_master.csv | awk '{print substr($1,1,12)}')"
RUN_TS="$(date +%Y%m%d-%H%M%S)"
if [[ -z "${RUN_ID}" ]]; then
  RUN_ID="${RUN_TS}-${MASTER_SHA}"
fi
if [[ -z "${RUN_SLUG}" ]]; then
  RUN_SLUG="$(date +%Y%m%d-%H%M)-${MASTER_SHA:0:8}"
fi

export RUN_ID
export RUN_SLUG
export RUN_SNAPSHOT_DIR="${REPO}/results/_snapshots/${RUN_ID}"
export RUN_STATE_DIR="${RUN_SNAPSHOT_DIR}/state"
export VLM_CACHE_DIR="${RUN_SNAPSHOT_DIR}/working/vlm_cache"
export VLM_IMG_CACHE_DIR="${RUN_SNAPSHOT_DIR}/working/vlm_imgcache"
export VLM_USAGE_LOG="${RUN_SNAPSHOT_DIR}/working/vlm_usage.csv"
export DIFY_DATASET_VLM_NAME="RAG-JA-${RUN_SLUG}-vlm"
export DIFY_DATASET_NOVLM_NAME="RAG-JA-${RUN_SLUG}-novlm"
export DIFY_DOCKER_COMPOSE="${DIFY_DOCKER_COMPOSE:-${REPO}/../dify_rag/dify/docker/docker-compose.yaml}"

mkdir -p "${RUN_STATE_DIR}" "${RUN_SNAPSHOT_DIR}/working"
python3 "${REPO}/scripts/run_snapshot.py" create --run-id "${RUN_ID}" --run-slug "${RUN_SLUG}"

pause_for_model() {
  local message="$1"
  echo
  echo "======================================================================"
  echo "${message}"
  echo "======================================================================"
  read -r -p "準備ができたら Enter を押してください: " _
}

if [[ "${SKIP_DOWNLOAD}" -eq 0 ]]; then
  python3 "${REPO}/repro/download_documents.py"
fi

if [[ ! -d documents ]] || [[ -z "$(find documents -maxdepth 1 -type f -name '*.pdf' -print -quit)" ]]; then
  echo "ERROR: documents/ にPDFがありません。download stepを確認してください。" >&2
  exit 1
fi

(
  cd documents
  shasum -a 256 -c ../repro/documents_checksums.sha256
)

pause_for_model "LM Studioで VLM=${VLM_MODEL:-qwen/qwen3-vl-8b} と embedding=${DIFY_EMBEDDING_MODEL:-Qwen/Qwen3-Embedding-8B-GGUF} を利用可能にしてください。"

if [[ "${SKIP_INGEST}" -eq 0 ]]; then
  "${REPO}/scripts/run_r1_r4_ingest.sh" all --no-purge
fi

python3 "${REPO}/scripts/dify_resources.py" dataset-summary \
  --name "${DIFY_DATASET_VLM_NAME}" \
  --out "${RUN_SNAPSHOT_DIR}/dify_dataset_vlm_summary.json"
python3 "${REPO}/scripts/dify_resources.py" dataset-summary \
  --name "${DIFY_DATASET_NOVLM_NAME}" \
  --out "${RUN_SNAPSHOT_DIR}/dify_dataset_novlm_summary.json"
python3 "${REPO}/scripts/dify_resources.py" validate-dataset \
  --name "${DIFY_DATASET_VLM_NAME}" \
  --out "${RUN_SNAPSHOT_DIR}/dify_dataset_vlm_retrieve.json"
python3 "${REPO}/scripts/dify_resources.py" validate-dataset \
  --name "${DIFY_DATASET_NOVLM_NAME}" \
  --out "${RUN_SNAPSHOT_DIR}/dify_dataset_novlm_retrieve.json"

KEY_ENV="${RUN_STATE_DIR}/dify_app_keys.env"
: > "${KEY_ENV}"
chmod 600 "${KEY_ENV}"

export DIFY_MANIFEST_R1="${RUN_SNAPSHOT_DIR}/dify_app_r1.json"
export DIFY_MANIFEST_R2="${RUN_SNAPSHOT_DIR}/dify_app_r2.json"
export DIFY_MANIFEST_R3="${RUN_SNAPSHOT_DIR}/dify_app_r3.json"
export DIFY_MANIFEST_R4="${RUN_SNAPSHOT_DIR}/dify_app_r4.json"

if [[ "${SKIP_APPS}" -eq 0 ]]; then
  if [[ -z "${DIFY_CONSOLE_CSRF_TOKEN:-}" && -f "${DIFY_DOCKER_COMPOSE}" ]]; then
    CONSOLE_ENV="${RUN_STATE_DIR}/dify_console_tokens.env"
    "${REPO}/scripts/dify_console_token_from_docker.sh" \
      --compose-file "${DIFY_DOCKER_COMPOSE}" \
      --out "${CONSOLE_ENV}"
    # shellcheck disable=SC1090
    source "${CONSOLE_ENV}"
  fi
  python3 "${REPO}/scripts/dify_resources.py" ensure-app \
    --run r1 --run-slug "${RUN_SLUG}" \
    --dataset-name "${DIFY_DATASET_NOVLM_NAME}" \
    --generation-model "openai/gpt-oss-20b" \
    --out "${DIFY_MANIFEST_R1}" \
    --key-env "${KEY_ENV}" \
    --env-name DIFY_APP_API_KEY_R1
  python3 "${REPO}/scripts/dify_resources.py" ensure-app \
    --run r2 --run-slug "${RUN_SLUG}" \
    --dataset-name "${DIFY_DATASET_VLM_NAME}" \
    --generation-model "openai/gpt-oss-20b" \
    --out "${DIFY_MANIFEST_R2}" \
    --key-env "${KEY_ENV}" \
    --env-name DIFY_APP_API_KEY_R2
  python3 "${REPO}/scripts/dify_resources.py" ensure-app \
    --run r3 --run-slug "${RUN_SLUG}" \
    --dataset-name "${DIFY_DATASET_NOVLM_NAME}" \
    --generation-model "qwen/qwen3.6-35b-a3b" \
    --out "${DIFY_MANIFEST_R3}" \
    --key-env "${KEY_ENV}" \
    --env-name DIFY_APP_API_KEY_R3
  python3 "${REPO}/scripts/dify_resources.py" ensure-app \
    --run r4 --run-slug "${RUN_SLUG}" \
    --dataset-name "${DIFY_DATASET_VLM_NAME}" \
    --generation-model "qwen/qwen3.6-35b-a3b" \
    --out "${DIFY_MANIFEST_R4}" \
    --key-env "${KEY_ENV}" \
    --env-name DIFY_APP_API_KEY_R4
fi

# shellcheck disable=SC1090
source "${KEY_ENV}"

pause_for_model "LM Studioで openai/gpt-oss-20b をロードし、qwen/qwen3.6-35b-a3b はunloadしてください。"
"${REPO}/scripts/run_r1_r4_chatbot.sh" r1 generate --fresh
"${REPO}/scripts/run_r1_r4_chatbot.sh" r2 generate --fresh

pause_for_model "LM Studioで openai/gpt-oss-20b をunloadし、qwen/qwen3.6-35b-a3b をロードしてください。"
"${REPO}/scripts/run_r1_r4_chatbot.sh" r1 after-judge
"${REPO}/scripts/run_r1_r4_chatbot.sh" r2 after-judge
"${REPO}/scripts/run_r1_r4_chatbot.sh" r3 all --fresh
"${REPO}/scripts/run_r1_r4_chatbot.sh" r4 all --fresh

python3 "${REPO}/scripts/analysis/analysis_r1_r4_current.py"
python3 "${REPO}/scripts/analysis/analysis_r1_r4_answer_traits.py"
python3 "${REPO}/scripts/run_snapshot.py" capture --run-id "${RUN_ID}"
python3 "${REPO}/scripts/run_snapshot.py" verify --out "${RUN_SNAPSHOT_DIR}/verification.json"

cat <<MSG

r1-r4 regeneration finished.
run_id: ${RUN_ID}
snapshot: ${RUN_SNAPSHOT_DIR}

MSG
