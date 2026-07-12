#!/usr/bin/env python3
"""Generate the current r1-r4 2x2 comparison report."""
from __future__ import annotations

import csv
import datetime as dt
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
OUT = ROOT / "analysis" / "analysis_r1_r4_current.md"

RUNS = {
    "r1": {"model": "gpt-oss-20b", "vlm": "なし"},
    "r2": {"model": "gpt-oss-20b", "vlm": "あり"},
    "r3": {"model": "qwen3.6-35b", "vlm": "なし"},
    "r4": {"model": "qwen3.6-35b", "vlm": "あり"},
}
TYPES = ("paragraph", "table", "image")


def read_judged(run: str) -> list[dict[str, str]]:
    path = RESULTS / run / "judged.csv"
    by_idx: dict[int, dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            by_idx[int(row["idx"])] = row
    return [by_idx[i] for i in sorted(by_idx)]


def score(rows: list[dict[str, str]]) -> tuple[int, int, float]:
    n = len(rows)
    ok = sum(1 for row in rows if row.get("ox") == "O")
    return ok, n, ok / n if n else 0.0


def fmt_score(rows: list[dict[str, str]], with_count: bool = True) -> str:
    ok, n, value = score(rows)
    if with_count:
        return f"{value:.3f}（{ok}/{n}）"
    return f"{value:.3f}"


def run_type_scores(rows: list[dict[str, str]]) -> dict[str, str]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["type"]].append(row)
    return {t: fmt_score(grouped[t], with_count=False) for t in TYPES}


def mcnemar(rows_a: list[dict[str, str]], rows_b: list[dict[str, str]]) -> tuple[int, int, int, float]:
    by_a = {int(row["idx"]): row for row in rows_a}
    by_b = {int(row["idx"]): row for row in rows_b}
    a_only = b_only = 0
    for idx in sorted(set(by_a) & set(by_b)):
        a_ok = by_a[idx].get("ox") == "O"
        b_ok = by_b[idx].get("ox") == "O"
        if a_ok and not b_ok:
            a_only += 1
        elif b_ok and not a_ok:
            b_only += 1
    n = a_only + b_only
    if n == 0:
        p = 1.0
    else:
        lo = min(a_only, b_only)
        tail = sum(math.comb(n, i) for i in range(lo + 1)) / (2 ** n)
        p = min(1.0, 2 * tail)
    return a_only, b_only, b_only - a_only, p


def image_pair_delta(rows_a: list[dict[str, str]], rows_b: list[dict[str, str]]) -> tuple[int, int, int]:
    img_a = [row for row in rows_a if row["type"] == "image"]
    img_b = [row for row in rows_b if row["type"] == "image"]
    a_only, b_only, delta, _ = mcnemar(img_a, img_b)
    return a_only, b_only, delta


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    out.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(out)


def main() -> None:
    judged = {run: read_judged(run) for run in RUNS}
    totals = {run: score(rows) for run, rows in judged.items()}
    best_run = max(RUNS, key=lambda run: totals[run][0])
    best_score = fmt_score(judged[best_run])

    pair_defs = [
        ("VLM効果、gpt-oss（r2対r1）", "r1", "r2"),
        ("VLM効果、qwen3.6（r4対r3）", "r3", "r4"),
        ("モデル差、VLMなし（r3対r1）", "r1", "r3"),
        ("モデル差、VLMあり（r4対r2）", "r2", "r4"),
    ]
    pairs = []
    for label, base, plus in pair_defs:
        base_only, plus_only, delta, p = mcnemar(judged[base], judged[plus])
        pairs.append((label, base, plus, base_only, plus_only, delta, p))

    type_rows = []
    for run, rows in judged.items():
        ts = run_type_scores(rows)
        type_rows.append([
            run,
            RUNS[run]["model"],
            RUNS[run]["vlm"],
            f"**{fmt_score(rows)}**",
            ts["paragraph"],
            ts["table"],
            ts["image"],
        ])

    pair_rows = [
        [
            label,
            f"{plus}のみ{plus_only}",
            f"{base}のみ{base_only}",
            f"**{delta:+d}**",
            f"{p:.3f}",
        ]
        for label, base, plus, base_only, plus_only, delta, p in pairs
    ]

    img_g_base, img_g_plus, img_g_delta = image_pair_delta(judged["r1"], judged["r2"])
    img_q_base, img_q_plus, img_q_delta = image_pair_delta(judged["r3"], judged["r4"])

    lines = [
        "# r1-r4 現行実験の2x2比較",
        "",
        f"作成: {dt.date.today().isoformat()}",
        "対象: `results/r1` から `r4` の現行成果物のみ",
        "目的: 公開記事で使う比較を、過去試行の結果に依存せず確定する。",
        "",
        "## 結論",
        "",
        "現行の公開実験は、生成モデル2種とVLM図表化の有無を組み合わせた2x2比較である。",
        f"最高値は{best_run}の **{best_score}**だった。",
        "",
        f"VLM図表化の効果は、gpt-ossで **{pairs[0][5]:+d}問**、qwen3.6で **{pairs[1][5]:+d}問**だった。",
        f"特にimage設問では、gpt-ossで **{img_g_delta:+d}問**、qwen3.6で **{img_q_delta:+d}問**だった。",
        "",
        f"生成モデルをgpt-oss-20bからqwen3.6-35bへ替えた差は、VLMありで **{pairs[3][5]:+d}問**、VLMなしで **{pairs[2][5]:+d}問**だった。",
        "この2比較では、一方向の優位を確認できたかはJudge条件込みで読む必要がある。",
        "",
        "したがって、公開記事での中心命題は次の範囲に限定する。",
        "",
        "> この固定評価系で比較した2要因のうち、VLM図表化の効果と生成モデル差を同じ条件で観測した。",
        "",
        "「あらゆるRAGでパーサが最大のレバー」「検索まで含めて自前実験で実証した」とは主張しない。",
        "",
        "## 2x2実験表",
        "",
        md_table(["run", "生成モデル", "VLM図表化", "総合", "paragraph", "table", "image"], type_rows),
        "",
        "## 対応のある比較",
        "",
        md_table(["比較", "一方のみ正答", "他方のみ正答", "純差", "McNemar exact p"], pair_rows),
        "",
        "p値は探索的な補助指標であり、多重比較補正はしていない。",
        "記事では点推定とidx単位の入れ替わりを主に示し、有意差だけで結論を作らない。",
        "",
        f"image設問に限ると、VLMありのみ正答／なしのみ正答は、gpt-ossで{img_g_plus}対{img_g_base}、qwen3.6で{img_q_plus}対{img_q_base}だった。",
        "",
        "## 比較条件",
        "",
        "- r1とr3は同じno-VLMナレッジを使う。",
        "- r2とr4は同じVLMナレッジを使う。",
        "- Judgeは全runで`qwen/qwen3.6-35b-a3b`に固定した。",
        "- r3とr4では生成とJudgeが同一モデルであり、自己選好や誤りの相関を排除できない。",
        "- O/Xは人手で確定した真値ではない。生成モデル差は、このJudge条件下の結果として扱う。",
        "",
        "## 公開記事での扱い",
        "",
        "- 実験結果として載せるrunはr1-r4だけとする。",
        "- この公開成果物に含めていない過去試行の数値や倍率を、現行実験の根拠や比較対象として載せない。",
        "- リーダーボード18構成の再集計は外部公開データの二次分析として分離し、r1-r4の実験結果と混同しない。",
        "- ToUnicode対策やDify運用上の注意は、r1-r4で採用した実装の説明として扱う。独立した効果量は主張しない。",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
