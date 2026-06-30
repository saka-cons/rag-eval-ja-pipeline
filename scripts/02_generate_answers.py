#!/usr/bin/env python3
"""rag_evaluation_master.csv の300問を Dify チャットアプリに投げ、回答を収集する。

設問・正解は master CSV の整備済み列(question_new / target_answer_new /
target_page_no_new)を使う。answers.csv へは既存スキーマの question / target_answer /
target_page_no 列にこの整備済み値を書き込むので、03/04 は変更なしで動く。

前提:
  - Dify でナレッジを紐付けたチャットボットアプリを作成・公開済み
  - そのアプリの API キー (app-xxxx)

使い方:
  export DIFY_APP_API_KEY=app-xxxx
  python 02_generate_answers.py --limit 10            # スモークテスト
  python 02_generate_answers.py                       # 全300問
  python 02_generate_answers.py --domain finance      # 1ドメインのみ

中断しても再実行すれば未回答の質問だけ続行する(レジューム対応)。
"""
import argparse
import csv
import os
import re
import sys
import time
from pathlib import Path

import requests

BASE_URL = os.environ.get("DIFY_BASE_URL", "http://localhost").rstrip("/")
API_KEY = os.environ.get("DIFY_APP_API_KEY")

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_CSV = ROOT / "rag_evaluation_master.csv"
OUT_DIR = ROOT / "results"

FIELDS = ["idx", "domain", "type", "target_file_name", "target_page_no",
          "question", "target_answer", "answer", "latency_sec",
          "prompt_tokens", "completion_tokens", "total_tokens", "error"]


def ask(question: str, timeout: int = 600, retries: int = 2, wait: int = 60) -> tuple[str, dict]:
    last_err = ""
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(wait)  # 前のリクエストが LM Studio 側に残っていても掃けるのを待つ
        r = requests.post(
            f"{BASE_URL}/v1/chat-messages",
            headers={"Authorization": f"Bearer {API_KEY}"},
            # auto_generate_name=False: Dify の会話名自動生成(回答後にシステムモデルを呼ぶ)を止める。
            # 生成LLM≠システムモデル時にこれが別モデルを常駐させ、LM Studio のメモリを圧迫して
            # retrieval のクエリ埋め込みが追い出され 0チャンク化する(回答内容には影響しない)。
            json={"inputs": {}, "query": question, "response_mode": "blocking",
                  "user": "rag-eval", "conversation_id": "", "auto_generate_name": False},
            timeout=timeout,
        )
        if r.ok:
            data = r.json()
            # Dify は思考型モデルの推論を <think> タグ付きで answer に含めるため除去する
            answer = re.sub(r"^\s*<think>.*?</think>\s*", "", data["answer"], flags=re.DOTALL)
            # metadata.usage に LM Studio 由来の token 数(prompt/completion/total)が入る
            usage = (data.get("metadata") or {}).get("usage") or {}
            return answer, usage
        last_err = f"{r.status_code} {r.text[:300]}"
    raise RuntimeError(last_err)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="先頭N問のみ実行(0=全件)")
    ap.add_argument("--domain", default="", help="特定ドメインのみ (finance/it/manufacturing/public/retail)")
    ap.add_argument("--out", default="answers.csv")
    args = ap.parse_args()

    if not API_KEY:
        print("ERROR: 環境変数 DIFY_APP_API_KEY を設定してください", file=sys.stderr)
        sys.exit(1)
    if not QUESTIONS_CSV.exists():
        print(
            "ERROR: rag_evaluation_master.csv がありません。\n"
            "Hugging Face dataset repo から取得し、このGitHub repoのルートへ配置してください。\n"
            "  cp /path/to/rag_evaluation_master.csv ./rag_evaluation_master.csv",
            file=sys.stderr,
        )
        sys.exit(1)

    rows = list(csv.DictReader(open(QUESTIONS_CSV, encoding="utf-8")))
    targets = [(i, r) for i, r in enumerate(rows)
               if not args.domain or r["domain"] == args.domain]
    if args.limit:
        targets = targets[: args.limit]

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / args.out
    done = set()
    if out_path.exists():
        done = {int(r["idx"]) for r in csv.DictReader(open(out_path, encoding="utf-8")) if not r["error"]}
        print(f"レジューム: {len(done)} 問は回答済み")

    new_file = not out_path.exists()
    with open(out_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for n, (idx, r) in enumerate(targets, 1):
            if idx in done:
                continue
            t0 = time.time()
            answer, error, usage = "", "", {}
            try:
                answer, usage = ask(r["question_new"])
            except Exception as e:
                error = str(e)[:300]
            dt = round(time.time() - t0, 1)
            w.writerow({"idx": idx, "domain": r["domain"], "type": r["type"],
                        "target_file_name": r["target_file_name"],
                        "target_page_no": r["target_page_no_new"],
                        "question": r["question_new"], "target_answer": r["target_answer_new"],
                        "answer": answer, "latency_sec": dt,
                        "prompt_tokens": usage.get("prompt_tokens", ""),
                        "completion_tokens": usage.get("completion_tokens", ""),
                        "total_tokens": usage.get("total_tokens", ""),
                        "error": error})
            f.flush()
            status = "ERR" if error else "OK"
            tok = usage.get("total_tokens", "?")
            print(f"[{n}/{len(targets)}] idx={idx} {r['domain']}/{r['type']} {status} ({dt}s, {tok}tok)")

    print(f"\n完了: {out_path}")


if __name__ == "__main__":
    main()
