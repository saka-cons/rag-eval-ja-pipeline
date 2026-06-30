#!/usr/bin/env python3
"""判定結果をドメイン別・タイプ別に集計し、参考表として表示する。

使い方:
  python 04_report.py
  python 04_report.py --in judged.csv --label "Dify (gpt-oss-20b)"
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "results"

DOMAINS = ["finance", "it", "manufacturing", "public", "retail"]
DOMAIN_JA = {"finance": "金融", "it": "情報通信", "manufacturing": "製造業",
             "public": "公共", "retail": "流通・小売"}

# 参照元データセットの公開値(参考。HF: allganize/RAG-Evaluation-Dataset-JA)。
# judge / tool-model / target columns が異なるため同一リーダーボードとしては扱わない。
REFERENCE = [
    ("Alli (claude3.5-sonnet)", {"finance": 0.833, "it": 0.933, "manufacturing": 0.717,
                                  "public": 0.883, "retail": 0.95}, 0.863),
    ("Alli (gpt-4o)", {"finance": 0.8, "it": 0.917, "manufacturing": 0.75,
                        "public": 0.833, "retail": 0.867}, 0.833),
    # gpt-4o-mini 系(生成LLM比較の主対象)
    ("Alli (gpt-4o-mini)", {"finance": 0.733, "it": 0.883, "manufacturing": 0.667,
                            "public": 0.767, "retail": 0.867}, 0.783),
    ("OpenAI Assistant (gpt-4o-mini)", {"finance": 0.683, "it": 0.85, "manufacturing": 0.717,
                                        "public": 0.75, "retail": 0.767}, 0.753),
    ("Langchain (gpt-4o-mini)", {"finance": 0.667, "it": 0.717, "manufacturing": 0.717,
                                  "public": 0.733, "retail": 0.767}, 0.72),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", default="judged.csv")
    ap.add_argument("--label", default="Local RAG")
    args = ap.parse_args()

    # 同一idxの重複行(再判定の追記)は最後の行を採用
    by_idx = {}
    for r in csv.DictReader(open(OUT_DIR / args.infile, encoding="utf-8")):
        by_idx[int(r["idx"])] = r
    rows = [by_idx[k] for k in sorted(by_idx)]
    unjudged = [r for r in rows if r["ox"] not in ("O", "X")]
    if unjudged:
        print(f"注意: 判定不能 {len(unjudged)} 件は X として集計します\n")

    by_domain = defaultdict(lambda: [0, 0])  # domain -> [O数, 総数]
    by_type = defaultdict(lambda: [0, 0])
    for r in rows:
        ok = 1 if r["ox"] == "O" else 0
        by_domain[r["domain"]][0] += ok
        by_domain[r["domain"]][1] += 1
        by_type[r["type"]][0] += ok
        by_type[r["type"]][1] += 1

    total_o = sum(v[0] for v in by_domain.values())
    total_n = sum(v[1] for v in by_domain.values())

    def fmt(o, n):
        return f"{o/n:.3f} ({o}/{n})" if n else "-"

    print("## ドメイン別スコア\n")
    header = "| RAG | " + " | ".join(DOMAIN_JA[d] for d in DOMAINS) + " | Average |"
    print(header)
    print("|" + "---|" * (len(DOMAINS) + 2))
    cells = [fmt(*by_domain[d]) for d in DOMAINS]
    print(f"| **{args.label}** | " + " | ".join(cells) + f" | **{fmt(total_o, total_n)}** |")
    for name, scores, avg in REFERENCE:
        cells = [f"{scores[d]:.3f}" for d in DOMAINS]
        print(f"| {name} (参考) | " + " | ".join(cells) + f" | {avg:.3f} |")

    print("\n## 質問タイプ別スコア\n")
    print("| type | score |")
    print("|---|---|")
    for t in ("paragraph", "table", "image"):
        if t in by_type:
            print(f"| {t} | {fmt(*by_type[t])} |")


if __name__ == "__main__":
    main()
