#!/usr/bin/env python3
"""Aggregate answer-text traits for the current r1-r4 evaluation runs.

Inputs:
  results/r{1,2,3,4}/judged.csv

Outputs:
  analysis/r1_r4_answer_traits_summary.csv
  analysis/r1_r4_answer_traits_by_type.csv
  analysis/r1_r4_answer_traits_by_ox.csv
  analysis/r1_r4_answer_traits_contrasts.csv
  analysis/r1_r4_answer_traits_per_question.csv
  analysis/analysis_r1_r4_answer_traits.md
"""

from __future__ import annotations

import csv
import datetime as dt
import re
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "results"
OUT_DIR = ROOT / "analysis"

RUNS = {
    "r1": {"model": "gpt-oss-20b", "vlm": "なし"},
    "r2": {"model": "gpt-oss-20b", "vlm": "あり"},
    "r3": {"model": "qwen3.6-35b", "vlm": "なし"},
    "r4": {"model": "qwen3.6-35b", "vlm": "あり"},
}

TYPE_ORDER = ["paragraph", "table", "image", "ALL"]
OX_ORDER = ["O", "X", "ALL"]

NUM_RE = re.compile(r"\d[\d,]*\.?\d*")
BRACKET_CITE_RE = re.compile(r"\[\d+\]")
JP_CITE_RE = re.compile(r"【[^】]*†[^】]*】")
SUPPORT_WORD_RE = re.compile(r"(根拠|引用|出典|source)", re.IGNORECASE)

ABSTAIN_KEYS = [
    "記載されていません",
    "情報がありません",
    "見つかりません",
    "確認できません",
    "記載がありません",
    "含まれていません",
    "情報は提供されていません",
    "特定できません",
    "わかりません",
    "分かりません",
    "明らかになりません",
    "明らかではありません",
]


def nums(text: str) -> set[float]:
    out: set[float] = set()
    for raw in NUM_RE.findall(str(text)):
        try:
            out.add(float(raw.replace(",", "")))
        except ValueError:
            pass
    return out


def numcov(target: str, answer: str) -> float | None:
    target_nums = nums(target)
    if not target_nums:
        return None
    return len(target_nums & nums(answer)) / len(target_nums)


def has_cite_marker(text: str) -> bool:
    text = str(text)
    return bool(BRACKET_CITE_RE.search(text) or JP_CITE_RE.search(text))


def has_support_word(text: str) -> bool:
    return bool(SUPPORT_WORD_RE.search(str(text)))


def is_abstain(text: str) -> bool:
    text = str(text)
    return any(key in text for key in ABSTAIN_KEYS)


def pct(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.1f}"


def avg(values: list[float]) -> float | None:
    return mean(values) if values else None


def read_run(run: str) -> list[dict[str, str]]:
    path = RESULTS_DIR / run / "judged.csv"
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def row_features(row: dict[str, str]) -> dict[str, object]:
    answer = row["answer"]
    cov = numcov(row["target_answer"], answer)
    return {
        "idx": row["idx"],
        "domain": row["domain"],
        "type": row["type"],
        "ox": row["ox"],
        "numcov": cov,
        "numeric_target": cov is not None,
        "has_cite_marker": has_cite_marker(answer),
        "has_support_word": has_support_word(answer),
        "abstain": is_abstain(answer),
        "answer_len": len(answer),
        "answer_numcount": len(NUM_RE.findall(answer)),
    }


def summarize(rows: list[dict[str, object]], run: str, group: str = "ALL") -> dict[str, object]:
    n = len(rows)
    covs = [r["numcov"] for r in rows if r["numcov"] is not None]
    correct_covs = [r["numcov"] for r in rows if r["numcov"] is not None and r["ox"] == "O"]
    wrong_covs = [r["numcov"] for r in rows if r["numcov"] is not None and r["ox"] == "X"]
    return {
        "run": run,
        "生成モデル": RUNS[run]["model"],
        "VLM図表化": RUNS[run]["vlm"],
        "group": group,
        "n": n,
        "正答数": sum(1 for r in rows if r["ox"] == "O"),
        "正答率_pct": round(sum(1 for r in rows if r["ox"] == "O") / n * 100, 1) if n else None,
        "数値target_n": len(covs),
        "正解数値一致率_pct": round(avg(covs) * 100, 1) if covs else None,
        "正答時_正解数値一致率_pct": round(avg(correct_covs) * 100, 1) if correct_covs else None,
        "誤答時_正解数値一致率_pct": round(avg(wrong_covs) * 100, 1) if wrong_covs else None,
        "引用マーカーあり率_pct": round(
            sum(1 for r in rows if r["has_cite_marker"]) / n * 100, 1
        )
        if n
        else None,
        "根拠語あり率_pct": round(
            sum(1 for r in rows if r["has_support_word"]) / n * 100, 1
        )
        if n
        else None,
        "棄権率_pct": round(sum(1 for r in rows if r["abstain"]) / n * 100, 1) if n else None,
        "平均回答長": round(avg([r["answer_len"] for r in rows])) if n else None,
        "平均数値出現数": round(avg([r["answer_numcount"] for r in rows]), 1) if n else None,
    }


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def md_table(rows: list[dict[str, object]], fields: list[str]) -> str:
    lines = [
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join("---" for _ in fields) + " |",
    ]
    for row in rows:
        vals = []
        for field in fields:
            value = row.get(field, "")
            if value is None:
                value = ""
            if isinstance(value, float):
                value = f"{value:.1f}"
            vals.append(str(value))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def build_contrasts(summary_by_run: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    pairs = [
        ("VLM効果 gpt-oss", "r2", "r1"),
        ("VLM効果 qwen3.6", "r4", "r3"),
        ("生成モデル差 VLMなし", "r3", "r1"),
        ("生成モデル差 VLMあり", "r4", "r2"),
    ]
    metrics = [
        "正答率_pct",
        "正解数値一致率_pct",
        "引用マーカーあり率_pct",
        "根拠語あり率_pct",
        "棄権率_pct",
        "平均回答長",
        "平均数値出現数",
    ]
    rows: list[dict[str, object]] = []
    for label, plus, base in pairs:
        row: dict[str, object] = {"比較": label, "差分": f"{plus} - {base}"}
        for metric in metrics:
            row[f"{metric}_差"] = round(
                float(summary_by_run[plus][metric]) - float(summary_by_run[base][metric]), 1
            )
        rows.append(row)
    return rows


def main() -> None:
    all_features: dict[str, list[dict[str, object]]] = {}
    per_question: dict[str, dict[str, object]] = {}

    for run in RUNS:
        source_rows = read_run(run)
        features = [row_features(row) for row in source_rows]
        all_features[run] = features
        for source, feat in zip(source_rows, features, strict=True):
            idx = source["idx"]
            item = per_question.setdefault(
                idx,
                {
                    "idx": idx,
                    "domain": source["domain"],
                    "type": source["type"],
                    "question": source["question"],
                    "target_answer": source["target_answer"],
                    "target_numcount": len(nums(source["target_answer"])),
                },
            )
            item[f"{run}_ox"] = feat["ox"]
            item[f"{run}_numcov_pct"] = (
                round(feat["numcov"] * 100, 1) if feat["numcov"] is not None else ""
            )
            item[f"{run}_has_cite_marker"] = int(bool(feat["has_cite_marker"]))
            item[f"{run}_has_support_word"] = int(bool(feat["has_support_word"]))
            item[f"{run}_abstain"] = int(bool(feat["abstain"]))
            item[f"{run}_answer_len"] = feat["answer_len"]
            item[f"{run}_answer_numcount"] = feat["answer_numcount"]

    summary_rows = [summarize(all_features[run], run) for run in RUNS]

    by_type_rows: list[dict[str, object]] = []
    for run in RUNS:
        for question_type in TYPE_ORDER:
            rows = (
                all_features[run]
                if question_type == "ALL"
                else [r for r in all_features[run] if r["type"] == question_type]
            )
            by_type_rows.append(summarize(rows, run, question_type))

    by_ox_rows: list[dict[str, object]] = []
    for run in RUNS:
        for ox in OX_ORDER:
            rows = all_features[run] if ox == "ALL" else [r for r in all_features[run] if r["ox"] == ox]
            by_ox_rows.append(summarize(rows, run, ox))

    summary_by_run = {row["run"]: row for row in summary_rows}
    contrast_rows = build_contrasts(summary_by_run)

    summary_fields = [
        "run",
        "生成モデル",
        "VLM図表化",
        "n",
        "正答数",
        "正答率_pct",
        "数値target_n",
        "正解数値一致率_pct",
        "正答時_正解数値一致率_pct",
        "誤答時_正解数値一致率_pct",
        "引用マーカーあり率_pct",
        "根拠語あり率_pct",
        "棄権率_pct",
        "平均回答長",
        "平均数値出現数",
    ]
    grouped_fields = ["run", "生成モデル", "VLM図表化", "group"] + summary_fields[3:]
    contrast_fields = [
        "比較",
        "差分",
        "正答率_pct_差",
        "正解数値一致率_pct_差",
        "引用マーカーあり率_pct_差",
        "根拠語あり率_pct_差",
        "棄権率_pct_差",
        "平均回答長_差",
        "平均数値出現数_差",
    ]
    per_question_fields = [
        "idx",
        "domain",
        "type",
        "target_numcount",
        "question",
        "target_answer",
    ]
    for run in RUNS:
        per_question_fields.extend(
            [
                f"{run}_ox",
                f"{run}_numcov_pct",
                f"{run}_has_cite_marker",
                f"{run}_has_support_word",
                f"{run}_abstain",
                f"{run}_answer_len",
                f"{run}_answer_numcount",
            ]
        )

    write_csv(OUT_DIR / "r1_r4_answer_traits_summary.csv", summary_rows, summary_fields)
    write_csv(OUT_DIR / "r1_r4_answer_traits_by_type.csv", by_type_rows, grouped_fields)
    write_csv(OUT_DIR / "r1_r4_answer_traits_by_ox.csv", by_ox_rows, grouped_fields)
    write_csv(OUT_DIR / "r1_r4_answer_traits_contrasts.csv", contrast_rows, contrast_fields)
    write_csv(
        OUT_DIR / "r1_r4_answer_traits_per_question.csv",
        [per_question[idx] for idx in sorted(per_question, key=lambda x: int(x))],
        per_question_fields,
    )

    md = f"""# r1-r4 回答テキスト指標の追試集計

作成: {dt.date.today().isoformat()}
対象: `results/r1` から `r4` の `judged.csv`
生成スクリプト: `scripts/analysis/analysis_r1_r4_answer_traits.py`

## 目的

L1/L2で使った回答テキスト指標を、現行r1-r4の結果に当て直す。
L1/L2では被測定ツールの内部構成や検索ログが分からないため補助指標として扱ったが、r1-r4は取込、検索、プロンプト、生成モデル、Judgeを固定して自分で回したパイプラインである。
ここでの結果はO/X正答率を置き換えるものではなく、この固定パイプラインの挙動が回答文にどう表れたかを見る観測指標である。

## 再現方法

```bash
cd {ROOT}
python3 scripts/analysis/analysis_r1_r4_answer_traits.py
```

## 定義

- **正解数値一致率**: `target_answer` から抽出した数値集合のうち、回答文にも現れる数値の割合。数値抽出は `\\d[\\d,]*\\.?\\d*`、カンマ除去後にfloat化して集合比較する。単位、%記号、単位換算、近似一致、漢数字変換は扱わない。
- **引用マーカーあり率**: L1/L2と同じく `[1]` や `【...†...】` 形式の引用マーカーを含む回答の割合。
- **根拠語あり率**: r1-r4回答では引用マーカーが出ないため、参考確認として `根拠`、`引用`、`出典`、`source` を含む回答の割合も出した。これは引用あり率とは別指標である。
- **棄権率**: `記載されていません`、`確認できません`、`特定できません`、`明らかではありません` など、根拠不足を示す定型表現を含む回答の割合。

## 全体集計

{md_table(summary_rows, summary_fields)}

## 差分

{md_table(contrast_rows, contrast_fields)}

## タイプ別

{md_table(by_type_rows, grouped_fields)}

## O/X別

{md_table(by_ox_rows, grouped_fields)}

## 読み方

- 正解数値一致率の対象は、数値を含む `target_answer` のみで、現行r1-r4では各run **186/300問**だった。
- 引用マーカーあり率は全runで0.0%だった。これは、今回のDify回答がL1/L2の公開CSV回答のような `[1]` / `【...†...】` 形式の引用を出していないためであり、根拠を使っていないことを意味しない。
- 正解数値一致率と棄権率は、r1-r4では自前パイプラインの挙動を読む観測指標として扱える。ただし、標準指標や単独の因果指標ではない。
- 根拠語あり率はr1-r4内の参考観察に留める。
- 棄権率は高ければよい指標ではない。必要な情報がある場面での過剰棄権と、根拠不足時に無理に答えない制御の両方を含む。
- 正解数値一致率も標準指標ではなく、回答テキストの傾向を見る簡易代理指標である。個別設問の厳密な意味一致を判定するものではない。

## 出力ファイル

- `analysis/r1_r4_answer_traits_summary.csv`
- `analysis/r1_r4_answer_traits_by_type.csv`
- `analysis/r1_r4_answer_traits_by_ox.csv`
- `analysis/r1_r4_answer_traits_contrasts.csv`
- `analysis/r1_r4_answer_traits_per_question.csv`
"""
    (OUT_DIR / "analysis_r1_r4_answer_traits.md").write_text(md, encoding="utf-8")

    print(f"wrote {OUT_DIR / 'analysis_r1_r4_answer_traits.md'}")
    print(md_table(summary_rows, summary_fields))


if __name__ == "__main__":
    main()
