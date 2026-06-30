#!/usr/bin/env python3
"""収集した回答を LM Studio 上の Judge LLM で O/X 判定する。

本家 Allganize Eval (answer_correctness) に倣い、正解回答と生成回答を比較して
事実として一致していれば O、欠落・矛盾があれば X と判定する。

前提:
  - LM Studio の OpenAI 互換 API サーバ起動済み (デフォルト http://localhost:1234/v1)
  - Judge 用モデルがロード済み (生成モデルとは別のモデルを推奨)

使い方:
  python 03_judge_answers.py --model qwen3-14b
  python 03_judge_answers.py --model qwen3-14b --in answers.csv --out judged.csv
"""
import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

import requests

LM_BASE = os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1").rstrip("/")

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "results"

JUDGE_PROMPT = """あなたはRAGシステムの回答品質を評価する厳格な採点者です。

[質問]
{question}

[正解回答]
{target_answer}

[評価対象の回答]
{answer}

評価対象の回答が、正解回答と照らして質問に正しく答えているか判定してください。

判定基準:
- 正解回答に含まれる主要な事実・数値・結論が評価対象の回答にも含まれていれば「O」
- 主要な事実が欠落している、数値が異なる、矛盾する内容がある、
  「分かりません」等の回答放棄をしている場合は「X」
- 表現の違いや追加情報は減点しない。事実の一致のみを評価する

必ず次のJSON形式のみで出力してください:
{{"reason": "判定理由を1文で", "judge": "O または X"}}"""


def call_judge(model: str, q: str, target: str, answer: str, max_tokens: int,
               temperature: float = 0.0) -> dict:
    r = requests.post(
        f"{LM_BASE}/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": JUDGE_PROMPT.format(
                question=q, target_answer=target, answer=answer)}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=600,
    )
    r.raise_for_status()
    return r.json()


def parse_judgment(resp: dict) -> tuple:
    choice = resp["choices"][0]
    finish = choice.get("finish_reason", "")
    msg = choice["message"]
    text = msg.get("content") or ""
    # 思考部分を除去 (reasoning モデル対応)
    if "</think>" in text:
        text = text.split("</think>")[-1]
    # max_tokens 到達 = 思考途中で切れて最終回答が無い
    if finish == "length":
        return "?", f"max_tokens到達で打ち切り: {text[-100:]}"
    # 最後に出現した JSON を採用 (プロンプトのテンプレ例のエコーを避ける)
    for raw in reversed(re.findall(r'\{[^{}]*"judge"[^{}]*\}', text, re.DOTALL)):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        j = str(obj.get("judge", "")).strip().upper()
        if j in ("O", "X"):
            return j, str(obj.get("reason", ""))[:200]
    # フォールバック: 末尾近くの O/X を拾う
    m = re.search(r'["\s]([OX])["\s}]*$', text.strip())
    if m:
        return m.group(1), "(JSON解析失敗・正規表現で抽出)"
    return "?", f"判定不能(finish={finish}): {text[-150:]}"


def judge_one(model: str, q: str, target: str, answer: str, max_tokens: int = 8192) -> tuple:
    if not answer.strip():
        return "X", "回答が空", {}
    # 主: temperature 0.0(決定論・再現性)。
    resp = call_judge(model, q, target, answer, max_tokens, temperature=0.0)
    ox, reason = parse_judgment(resp)
    # フォールバック: temp0 では推論モデルが反復ループに陥り max_tokens(例:32768)でも
    # verdict を出せない稀ケースがある。verdict 未到達(?)の時だけ temp0.3 で1回再判定する。
    if ox == "?":
        resp = call_judge(model, q, target, answer, max_tokens, temperature=0.3)
        ox, reason = parse_judgment(resp)
        if ox in ("O", "X"):
            reason = f"[temp0.3再判定] {reason}"
    return ox, reason, resp.get("usage") or {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="LM Studio にロード済みの Judge モデルID")
    ap.add_argument("--in", dest="infile", default="answers.csv")
    ap.add_argument("--out", default="judged.csv")
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--debug-idx", type=int, default=None,
                    help="指定idxを1件だけ判定し、生レスポンス全文を表示(ファイルには書かない)")
    ap.add_argument("--retry-failed", action="store_true",
                    help="既存judged.csvの '?' 行を再判定する")
    args = ap.parse_args()

    in_path = OUT_DIR / args.infile
    out_path = OUT_DIR / args.out
    if not in_path.exists():
        print(f"ERROR: {in_path} がありません。先に 02_generate_answers.py を実行してください", file=sys.stderr)
        sys.exit(1)

    # 同一idxの重複行(リトライ痕)は、回答のある最後の行を採用
    by_idx = {}
    for r in csv.DictReader(open(in_path, encoding="utf-8")):
        prev = by_idx.get(int(r["idx"]))
        if prev is None or r["answer"].strip() or not prev["answer"].strip():
            by_idx[int(r["idx"])] = r
    rows = [by_idx[k] for k in sorted(by_idx)]

    if args.debug_idx is not None:
        r = by_idx.get(args.debug_idx)
        if r is None:
            print(f"idx={args.debug_idx} が {in_path} にありません", file=sys.stderr)
            sys.exit(1)
        print(f"=== idx={r['idx']} answer({len(r['answer'])}文字) ===\n{r['answer'][:500]}\n")
        resp = call_judge(args.model, r["question"], r["target_answer"], r["answer"], args.max_tokens)
        choice = resp["choices"][0]
        print(f"=== finish_reason: {choice.get('finish_reason')} | usage: {resp.get('usage')} ===")
        if choice["message"].get("reasoning_content"):
            print(f"=== reasoning_content(末尾500字) ===\n...{choice['message']['reasoning_content'][-500:]}\n")
        print(f"=== content全文 ===\n{choice['message'].get('content')}\n")
        ox, reason = parse_judgment(resp)
        print(f"=== 判定: {ox} | {reason} ===")
        return

    done = set()
    if out_path.exists():
        keep = "OX" if args.retry_failed else "OX?"
        done = {int(r["idx"]) for r in csv.DictReader(open(out_path, encoding="utf-8"))
                if r["ox"] in tuple(keep)}
        print(f"レジューム: {len(done)} 問は判定済み")

    fields = ["idx", "domain", "type", "question", "target_answer", "answer", "ox", "judge_reason",
              "prompt_tokens", "completion_tokens", "total_tokens"]
    new_file = not out_path.exists()
    with open(out_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new_file:
            w.writeheader()
        for n, r in enumerate(rows, 1):
            if int(r["idx"]) in done:
                continue
            usage = {}
            try:
                ox, reason, usage = judge_one(args.model, r["question"], r["target_answer"],
                                              r["answer"], args.max_tokens)
            except Exception as e:
                ox, reason = "?", f"API error: {e}"
            w.writerow({"idx": r["idx"], "domain": r["domain"], "type": r["type"],
                        "question": r["question"], "target_answer": r["target_answer"],
                        "answer": r["answer"], "ox": ox, "judge_reason": reason,
                        "prompt_tokens": usage.get("prompt_tokens", ""),
                        "completion_tokens": usage.get("completion_tokens", ""),
                        "total_tokens": usage.get("total_tokens", "")})
            f.flush()
            print(f"[{n}/{len(rows)}] idx={r['idx']} {r['domain']}/{r['type']} -> {ox}")

    print(f"\n完了: {out_path}")


if __name__ == "__main__":
    main()
