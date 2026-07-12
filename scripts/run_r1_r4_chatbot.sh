#!/usr/bin/env bash
# r1-r4 の回答収集・Judge・集計・成果物整理を run 単位で実行する。
#
# run定義:
#   r1 = no-VLM knowledge + generation openai/gpt-oss-20b
#   r2 = VLM knowledge    + generation openai/gpt-oss-20b
#   r3 = no-VLM knowledge + generation qwen/qwen3.6-35b-a3b
#   r4 = VLM knowledge    + generation qwen/qwen3.6-35b-a3b
#
# 使い方:
#   # gpt-oss系は、生成後に qwen3.6 へロードを切り替えて after-judge を実行する
#   ./scripts/run_r1_r4_chatbot.sh r1 generate --fresh
#   ./scripts/run_r1_r4_chatbot.sh r1 after-judge
#
#   # qwen系は生成/Judgeが同一モデルなので all で通せる
#   ./scripts/run_r1_r4_chatbot.sh r3 all --fresh
#
# step:
#   generate    answers.csv を作る
#   judge       judged.csv を作る
#   report      04_report.py の出力を report.md に保存
#   finalize    analysis.md と cache snapshot を作る
#   after-judge judge + report + finalize
#   all         generate + judge + report + finalize。ただし r1/r2 は generate 後に停止
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -x "${REPO}/.venv/bin/python3" ]]; then
  export PATH="${REPO}/.venv/bin:${PATH}"
elif [[ -x "${REPO}/.venv/bin/python" ]]; then
  export PATH="${REPO}/.venv/bin:${PATH}"
fi

RUN="${1:-}"
STEP="${2:-}"
if [[ -z "${RUN}" || "${RUN}" == "--help" || "${RUN}" == "-h" ]]; then
  sed -n '1,24p' "$0"
  exit 0
fi
if [[ -z "${STEP}" ]]; then
  STEP="all"
fi
shift 2 || true

FRESH=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --fresh) FRESH=1 ;;
    *) echo "ERROR: unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

case "${RUN}" in
  r1)
    MODE="novlm"
    DATASET="${DIFY_DATASET_NOVLM_NAME:-RAG-Eval-JA-master-novlm}"
    GEN_MODEL="openai/gpt-oss-20b"
    JUDGE_MODEL="qwen/qwen3.6-35b-a3b"
    LABEL="r1: no-VLM + gpt-oss-20b"
    RUN_APP_API_KEY="${DIFY_APP_API_KEY_R1:-${DIFY_APP_API_KEY:-}}"
    DIFY_MANIFEST="${DIFY_MANIFEST_R1:-}"
    ;;
  r2)
    MODE="vlm"
    DATASET="${DIFY_DATASET_VLM_NAME:-RAG-Eval-JA-master-vlm}"
    GEN_MODEL="openai/gpt-oss-20b"
    JUDGE_MODEL="qwen/qwen3.6-35b-a3b"
    LABEL="r2: VLM + gpt-oss-20b"
    RUN_APP_API_KEY="${DIFY_APP_API_KEY_R2:-${DIFY_APP_API_KEY:-}}"
    DIFY_MANIFEST="${DIFY_MANIFEST_R2:-}"
    ;;
  r3)
    MODE="novlm"
    DATASET="${DIFY_DATASET_NOVLM_NAME:-RAG-Eval-JA-master-novlm}"
    GEN_MODEL="qwen/qwen3.6-35b-a3b"
    JUDGE_MODEL="qwen/qwen3.6-35b-a3b"
    LABEL="r3: no-VLM + qwen3.6-35b-a3b"
    RUN_APP_API_KEY="${DIFY_APP_API_KEY_R3:-${DIFY_APP_API_KEY:-}}"
    DIFY_MANIFEST="${DIFY_MANIFEST_R3:-}"
    ;;
  r4)
    MODE="vlm"
    DATASET="${DIFY_DATASET_VLM_NAME:-RAG-Eval-JA-master-vlm}"
    GEN_MODEL="qwen/qwen3.6-35b-a3b"
    JUDGE_MODEL="qwen/qwen3.6-35b-a3b"
    LABEL="r4: VLM + qwen3.6-35b-a3b"
    RUN_APP_API_KEY="${DIFY_APP_API_KEY_R4:-${DIFY_APP_API_KEY:-}}"
    DIFY_MANIFEST="${DIFY_MANIFEST_R4:-}"
    ;;
  *)
    echo "ERROR: run must be one of: r1, r2, r3, r4" >&2
    exit 2
    ;;
esac

case "${STEP}" in
  generate|judge|report|finalize|after-judge|all) ;;
  *) echo "ERROR: step must be generate, judge, report, finalize, after-judge, all" >&2; exit 2 ;;
esac

cd "${REPO}"
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

RUN_DIR="${REPO}/results/${RUN}"
ANSWERS_REL="${RUN}/answers.csv"
JUDGED_REL="${RUN}/judged.csv"
REPORT="${RUN_DIR}/report.md"

archive_run_dir() {
  if [[ ! -e "${RUN_DIR}" ]]; then
    return
  fi
  local archive_base="${RUN_SNAPSHOT_DIR:-${REPO}/results/_archived_fresh}"
  local stamp
  stamp="$(date +%Y%m%d-%H%M%S)"
  mkdir -p "${archive_base}/preexisting_results"
  mv "${RUN_DIR}" "${archive_base}/preexisting_results/${RUN}-${stamp}"
  echo "既存の ${RUN_DIR} は ${archive_base}/preexisting_results/${RUN}-${stamp} に退避しました。"
}

banner() {
  echo
  echo "======================================================================"
  echo "# ${RUN} ${STEP}"
  echo "# ${LABEL}"
  echo "======================================================================"
  echo "Dify chatbot context must be: ${DATASET}"
  echo "Generation model configured in Dify app: ${GEN_MODEL}"
  echo "Judge model loaded in LM Studio for judge step: ${JUDGE_MODEL}"
  echo
}

run_generate() {
  if [[ -z "${RUN_APP_API_KEY:-}" ]]; then
    echo "ERROR: per-run DIFY_APP_API_KEY for ${RUN} or DIFY_APP_API_KEY is required for generate" >&2
    exit 1
  fi
  if [[ "${FRESH}" -eq 1 ]]; then
    archive_run_dir
  fi
  mkdir -p "${RUN_DIR}"
  DIFY_APP_API_KEY="${RUN_APP_API_KEY}" python3 "${REPO}/scripts/02_generate_answers.py" --out "${ANSWERS_REL}"
}

run_judge() {
  if [[ ! -f "${RUN_DIR}/answers.csv" ]]; then
    echo "ERROR: ${RUN_DIR}/answers.csv not found. Run generate first." >&2
    exit 1
  fi
  python3 "${REPO}/scripts/03_judge_answers.py" \
    --model "${JUDGE_MODEL}" \
    --in "${ANSWERS_REL}" \
    --out "${JUDGED_REL}" \
    --max-tokens "${JUDGE_MAX_TOKENS:-32768}"
}

run_report() {
  if [[ ! -f "${RUN_DIR}/judged.csv" ]]; then
    echo "ERROR: ${RUN_DIR}/judged.csv not found. Run judge first." >&2
    exit 1
  fi
  python3 "${REPO}/scripts/04_report.py" --in "${JUDGED_REL}" --label "${LABEL}" | tee "${REPORT}"
}

run_finalize() {
  local finalize_cmd=(python3 "${REPO}/scripts/finalize_run_artifacts.py" "${RUN}" \
    --mode "${MODE}" \
    --dataset-name "${DATASET}" \
    --generation-model "${GEN_MODEL}" \
    --judge-model "${JUDGE_MODEL}")
  if [[ -n "${RUN_SNAPSHOT_DIR:-}" ]]; then
    finalize_cmd+=(--snapshot-dir "${RUN_SNAPSHOT_DIR}")
  fi
  if [[ -n "${DIFY_MANIFEST:-}" ]]; then
    finalize_cmd+=(--dify-manifest "${DIFY_MANIFEST}")
  fi
  "${finalize_cmd[@]}"
}

banner

case "${STEP}" in
  generate)
    run_generate
    ;;
  judge)
    run_judge
    ;;
  report)
    run_report
    ;;
  finalize)
    run_finalize
    ;;
  after-judge)
    run_judge
    run_report
    run_finalize
    ;;
  all)
    run_generate
    if [[ "${GEN_MODEL}" != "${JUDGE_MODEL}" ]]; then
      cat <<MSG

${RUN} は生成モデル(${GEN_MODEL})と Judge(${JUDGE_MODEL})を同時ロードできない想定です。
LM Studio で ${JUDGE_MODEL} をロードし、次を実行してください:

  ./scripts/run_r1_r4_chatbot.sh ${RUN} after-judge

MSG
      exit 0
    fi
    run_judge
    run_report
    run_finalize
    ;;
esac
