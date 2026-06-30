#!/usr/bin/env bash
# r1-r4 用の Dify ナレッジを作り直す。
#
# 生成されるナレッジ:
#   - RAG-Eval-JA-master-vlm   : r2/r4 用(VLM 図表テキスト化あり)
#   - RAG-Eval-JA-master-novlm : r1/r3 用(--no-vlm 対照)
#
# 使い方:
#   ./scripts/run_r1_r4_ingest.sh all
#   ./scripts/run_r1_r4_ingest.sh vlm
#   ./scripts/run_r1_r4_ingest.sh novlm
#   ./scripts/run_r1_r4_ingest.sh all --refresh
#
# 注意:
#   - 実行後、Dify のチャットボット「コンテキスト」を対象ナレッジへ手動で切り替える。
#   - VLM側は LM Studio で qwen/qwen3-vl-8b をロードしておく。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${SCRIPT_DIR}/.." && pwd)"

MODE="${1:-all}"
if [[ "${MODE}" == "--help" || "${MODE}" == "-h" ]]; then
  sed -n '1,16p' "$0"
  exit 0
fi
if [[ "${MODE}" != "all" && "${MODE}" != "vlm" && "${MODE}" != "novlm" ]]; then
  echo "ERROR: mode must be one of: all, vlm, novlm" >&2
  exit 2
fi
shift || true

REFRESH=0
PURGE=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --refresh) REFRESH=1 ;;
    --no-purge) PURGE=0 ;;
    *) echo "ERROR: unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

cd "${REPO}"
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -z "${DIFY_KNOWLEDGE_API_KEY:-}" ]]; then
  echo "ERROR: DIFY_KNOWLEDGE_API_KEY is required" >&2
  exit 1
fi

PYMUPDF_PYTHON="${PYMUPDF_PYTHON:-python3}"

if [[ ! -f "${REPO}/rag_evaluation_master.csv" ]]; then
  cat >&2 <<'MSG'
ERROR: rag_evaluation_master.csv がありません。
Hugging Face dataset repo から取得し、このGitHub repoのルートへ配置してください。

 cp /path/to/rag_evaluation_master.csv ./rag_evaluation_master.csv

参照元 rag_evaluation_result.csv から再生成する場合は、Hugging Face dataset repo 側の
build_master_csv.py を使ってください。
MSG
  exit 1
fi

run_ingest() {
  local kind="$1"
  local dataset="$2"
  shift 2

  echo
  echo "======================================================================"
  echo "# ingest ${kind}: ${dataset}"
  echo "======================================================================"

  local cmd=("${PYMUPDF_PYTHON}" "${REPO}/scripts/01_upload_documents_vlm.py")
  if [[ "${PURGE}" -eq 1 ]]; then
    cmd+=(--purge)
  fi
  if [[ "${REFRESH}" -eq 1 ]]; then
    cmd+=(--refresh)
  fi
  if [[ $# -gt 0 ]]; then
    cmd+=("$@")
  fi

  DIFY_DATASET_NAME="${dataset}" "${cmd[@]}"

  DIFY_DATASET_NAME="${dataset}" "${PYMUPDF_PYTHON}" "${REPO}/scripts/wait_indexing.py" \
    --interval "${WAIT_INTERVAL:-10}" \
    --timeout "${WAIT_TIMEOUT:-3600}" \
    --max-retry "${WAIT_MAX_RETRY:-2}"

  mkdir -p "${REPO}/results"
  DIFY_DATASET_NAME="${dataset}" "${PYMUPDF_PYTHON}" "${REPO}/scripts/01_upload_documents_vlm.py" \
    --embedding-usage > "${REPO}/results/ingest_${kind}_embedding_usage.txt"
}

case "${MODE}" in
  all)
    run_ingest "vlm" "RAG-Eval-JA-master-vlm"
    run_ingest "novlm" "RAG-Eval-JA-master-novlm" --no-vlm
    ;;
  vlm)
    run_ingest "vlm" "RAG-Eval-JA-master-vlm"
    ;;
  novlm)
    run_ingest "novlm" "RAG-Eval-JA-master-novlm" --no-vlm
    ;;
esac

cat <<'MSG'

取り込み完了。
次に Dify Studio のチャットボット設定で、実行する run に応じてコンテキストを切り替えてください。
  r1/r3: RAG-Eval-JA-master-novlm
  r2/r4: RAG-Eval-JA-master-vlm

その後、scripts/run_r1_r4_chatbot.sh を実行します。
MSG
