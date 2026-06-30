#!/usr/bin/env python3
"""2版の judged.csv を idx 突合し、純増減(O→X 悪化 / X→O 改善)を出す。

生成LLM入れ替え等の「版間の相対比較」用。総合だけでなく type/domain 別の純差も出す。
CLAUDE.md の方針(cherrypick 禁止・idx 突合で純増減)に従い、両版の全 idx を機械的に突合する。

使い方(scripts で / judged は results 相対パス):
  python3 compare_versions.py --base r1/judged.csv --new r2/judged.csv
  python3 compare_versions.py --base r1/judged.csv --new r2/judged.csv \
      --base-label "gpt-oss-20b no-VLM (r1)" --new-label "gpt-oss-20b VLM (r2)"
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "results"

DOMAINS = ["finance", "it", "manufacturing", "public", "retail"]
TYPES = ["paragraph", "table", "image"]


def load(path: Path) -> dict:
    """idx -> 行(同一idxの重複は最後を採用、04_report.py と同じ)。"""
    by_idx = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        by_idx[int(r["idx"])] = r
    return by_idx


def ok(row: dict) -> bool:
    """O のみ正解。?・X・欠損は不正解扱い(04_report.py と同じ集計規則)。"""
    return row["ox"] == "O"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="基準版の judged.csv(results 相対)")
    ap.add_argument("--new", required=True, help="比較版の judged.csv(results 相対)")
    ap.add_argument("--base-label", default=None)
    ap.add_argument("--new-label", default=None)
    args = ap.parse_args()

    base = load(OUT_DIR / args.base)
    new = load(OUT_DIR / args.new)
    base_label = args.base_label or args.base
    new_label = args.new_label or args.new

    common = sorted(set(base) & set(new))
    only_base = sorted(set(base) - set(new))
    only_new = sorted(set(new) - set(base))

    base_o = sum(ok(base[i]) for i in common)
    new_o = sum(ok(new[i]) for i in common)
    n = len(common)

    improved = [i for i in common if not ok(base[i]) and ok(new[i])]   # X→O
    regressed = [i for i in common if ok(base[i]) and not ok(new[i])]  # O→X

    print(f"## idx 突合: {new_label}  vs  {base_label}\n")
    print(f"- 突合対象: {n} 問(共通idx)")
    if only_base or only_new:
        print(f"- 片側のみ: base専用 {len(only_base)} / new専用 {len(only_new)}(集計から除外)")
    print(f"- 基準 {base_label}: **{base_o}/{n} ({base_o/n:.3f})**")
    print(f"- 比較 {new_label}: **{new_o}/{n} ({new_o/n:.3f})**")
    print(f"- 純増減: **{new_o - base_o:+d}** (改善 X→O {len(improved)} / 悪化 O→X {len(regressed)})\n")

    print(f"### 改善 X→O ({len(improved)})")
    print("  " + (", ".join(f"idx{i}({new[i]['type']}/{new[i]['domain']})" for i in improved) or "—"))
    print(f"\n### 悪化 O→X ({len(regressed)})")
    print("  " + (", ".join(f"idx{i}({new[i]['type']}/{new[i]['domain']})" for i in regressed) or "—"))

    # type / domain 別の純差(net = new側O数 − base側O数)
    def net_table(key: str, buckets: list):
        print(f"\n### {key} 別(共通idxのみ)\n")
        print(f"| {key} | {base_label} | {new_label} | 純差 |")
        print("|---|---|---|---|")
        bc = defaultdict(lambda: [0, 0, 0])  # bucket -> [base_O, new_O, n]
        for i in common:
            b = new[i][key]
            bc[b][0] += ok(base[i])
            bc[b][1] += ok(new[i])
            bc[b][2] += 1
        for b in buckets:
            if b in bc:
                bo, no, cnt = bc[b]
                print(f"| {b} | {bo}/{cnt} ({bo/cnt:.3f}) | {no}/{cnt} ({no/cnt:.3f}) | {no - bo:+d} |")

    net_table("type", TYPES)
    net_table("domain", DOMAINS)


if __name__ == "__main__":
    main()
