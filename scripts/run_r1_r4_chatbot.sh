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
    DATASET="RAG-Eval-JA-master-novlm"
    GEN_MODEL="openai/gpt-oss-20b"
    JUDGE_MODEL="qwen/qwen3.6-35b-a3b"
    LABEL="r1: no-VLM + gpt-oss-20b"
    ;;
  r2)
    MODE="vlm"
    DATASET="RAG-Eval-JA-master-vlm"
    GEN_MODEL="openai/gpt-oss-20b"
    JUDGE_MODEL="qwen/qwen3.6-35b-a3b"
    LABEL="r2: VLM + gpt-oss-20b"
    ;;
  r3)
    MODE="novlm"
    DATASET="RAG-Eval-JA-master-novlm"
    GEN_MODEL="qwen/qwen3.6-35b-a3b"
    JUDGE_MODEL="qwen/qwen3.6-35b-a3b"
    LABEL="r3: no-VLM + qwen3.6-35b-a3b"
    ;;
  r4)
    MODE="vlm"
    DATASET="RAG-Eval-JA-master-vlm"
    GEN_MODEL="qwen/qwen3.6-35b-a3b"
    JUDGE_MODEL="qwen/qwen3.6-35b-a3b"
    LABEL="r4: VLM + qwen3.6-35b-a3b"
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
  if [[ -z "${DIFY_APP_API_KEY:-}" ]]; then
    echo "ERROR: DIFY_APP_API_KEY is required for generate" >&2
    exit 1
  fi
  if [[ "${FRESH}" -eq 1 ]]; then
    rm -rf "${RUN_DIR}"
  fi
  mkdir -p "${RUN_DIR}"
  python3 "${REPO}/scripts/02_generate_answers.py" --out "${ANSWERS_REL}"
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
  python3 "${REPO}/scripts/finalize_run_artifacts.py" "${RUN}" \
    --mode "${MODE}" \
    --dataset-name "${DATASET}" \
    --generation-model "${GEN_MODEL}" \
    --judge-model "${JUDGE_MODEL}"
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
