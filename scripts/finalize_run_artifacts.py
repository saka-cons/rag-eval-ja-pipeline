#!/usr/bin/env python3
"""r1-r4 の再現用成果物を run ディレクトリへ集約する。

各 run ディレクトリに以下を揃える:
  - answers.csv / judged.csv (既存ファイルを前提)
  - analysis.md (集計・実行条件・再現メモ)
  - vlm_cache/ (run で使った Markdown キャッシュ)
  - vlm_imgcache/ (VLM run では画像応答キャッシュ、no-vlm run ではREADMEのみ)
"""
from __future__ import annotations

import argparse
import csv
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

RUNS = {
    "r1": {
        "mode": "novlm",
        "dataset": "RAG-Eval-JA-master-novlm",
        "generation_model": "openai/gpt-oss-20b",
        "judge_model": "qwen/qwen3.6-35b-a3b",
        "label": "r1: no-VLM + gpt-oss-20b",
    },
    "r2": {
        "mode": "vlm",
        "dataset": "RAG-Eval-JA-master-vlm",
        "generation_model": "openai/gpt-oss-20b",
        "judge_model": "qwen/qwen3.6-35b-a3b",
        "label": "r2: VLM + gpt-oss-20b",
    },
    "r3": {
        "mode": "novlm",
        "dataset": "RAG-Eval-JA-master-novlm",
        "generation_model": "qwen/qwen3.6-35b-a3b",
        "judge_model": "qwen/qwen3.6-35b-a3b",
        "label": "r3: no-VLM + qwen3.6-35b-a3b",
    },
    "r4": {
        "mode": "vlm",
        "dataset": "RAG-Eval-JA-master-vlm",
        "generation_model": "qwen/qwen3.6-35b-a3b",
        "judge_model": "qwen/qwen3.6-35b-a3b",
        "label": "r4: VLM + qwen3.6-35b-a3b",
    },
}

DOMAINS = ["finance", "it", "manufacturing", "public", "retail"]
TYPES = ["paragraph", "table", "image"]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def latest_by_idx(rows: list[dict]) -> list[dict]:
    by_idx = {}
    for row in rows:
        if row.get("idx", "").strip():
            by_idx[int(row["idx"])] = row
    return [by_idx[i] for i in sorted(by_idx)]


def score_tables(rows: list[dict]) -> tuple[str, str, str]:
    if not rows:
        return "判定結果なし。", "", ""

    by_domain = defaultdict(lambda: [0, 0])
    by_type = defaultdict(lambda: [0, 0])
    for row in rows:
        ok = 1 if row.get("ox") == "O" else 0
        by_domain[row["domain"]][0] += ok
        by_domain[row["domain"]][1] += 1
        by_type[row["type"]][0] += ok
        by_type[row["type"]][1] += 1

    total_o = sum(v[0] for v in by_domain.values())
    total_n = sum(v[1] for v in by_domain.values())

    def fmt(pair: list[int]) -> str:
        o, n = pair
        return f"{o / n:.3f} ({o}/{n})" if n else "-"

    summary = f"{total_o / total_n:.3f} ({total_o}/{total_n})" if total_n else "-"
    domain_lines = [
        "| domain | score |",
        "|---|---|",
        *[f"| {d} | {fmt(by_domain[d])} |" for d in DOMAINS],
    ]
    type_lines = [
        "| type | score |",
        "|---|---|",
        *[f"| {t} | {fmt(by_type[t])} |" for t in TYPES if by_type[t][1]],
    ]
    return summary, "\n".join(domain_lines), "\n".join(type_lines)


def copy_selected_cache(src: Path, dst: Path, mode: str) -> int:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        (dst / "README.md").write_text(
            f"# vlm_cache\n\nSource cache directory was not present: `{src}`.\n",
            encoding="utf-8",
        )
        return 0

    copied = 0
    for path in sorted(src.glob("*.md")):
        name = path.name
        if mode == "vlm":
            use = not (
                name.endswith(".novlm.md")
                or name.endswith(".pageimg.md")
            )
        else:
            use = name.endswith(".novlm.md")
        if use:
            shutil.copy2(path, dst / name)
            copied += 1
    if copied == 0:
        (dst / "README.md").write_text(
            f"# vlm_cache\n\nNo `{mode}` cache files were found in `{src}`.\n",
            encoding="utf-8",
        )
    return copied


def copy_img_cache(src: Path, dst: Path, mode: str) -> int:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    if mode != "vlm":
        (dst / "README.md").write_text(
            "# vlm_imgcache\n\nThis run uses `--no-vlm`; image response cache is not used.\n",
            encoding="utf-8",
        )
        return 0
    if not src.exists():
        (dst / "README.md").write_text(
            f"# vlm_imgcache\n\nSource image cache directory was not present: `{src}`.\n",
            encoding="utf-8",
        )
        return 0
    copied = 0
    for path in sorted(p for p in src.iterdir() if p.is_file()):
        shutil.copy2(path, dst / path.name)
        copied += 1
    if copied == 0:
        (dst / "README.md").write_text("# vlm_imgcache\n\nNo image cache files found.\n", encoding="utf-8")
    return copied


def write_analysis(run: str, cfg: dict, run_dir: Path, cache_count: int, img_count: int) -> None:
    answers = latest_by_idx(read_csv(run_dir / "answers.csv"))
    judged = latest_by_idx(read_csv(run_dir / "judged.csv"))
    summary, domain_table, type_table = score_tables(judged)
    errors = [r for r in answers if r.get("error")]
    ox_counts = Counter(r.get("ox", "?") for r in judged)
    token_prompt = sum(int(r.get("prompt_tokens") or 0) for r in answers)
    token_completion = sum(int(r.get("completion_tokens") or 0) for r in answers)
    judge_prompt = sum(int(r.get("prompt_tokens") or 0) for r in judged)
    judge_completion = sum(int(r.get("completion_tokens") or 0) for r in judged)

    lines = [
        f"# {run} analysis",
        "",
        f"- generated_at: {datetime.now().isoformat(timespec='seconds')}",
        f"- label: {cfg['label']}",
        f"- knowledge_mode: {cfg['mode']}",
        f"- dify_dataset_name: `{cfg['dataset']}`",
        f"- generation_model: `{cfg['generation_model']}`",
        f"- judge_model: `{cfg['judge_model']}`",
        f"- score: **{summary}**",
        f"- answers_rows: {len(answers)}",
        f"- judged_rows: {len(judged)}",
        f"- ox_counts: {dict(ox_counts)}",
        f"- answer_errors: {len(errors)}",
        f"- generation_tokens: prompt={token_prompt:,} / completion={token_completion:,}",
        f"- judge_tokens: prompt={judge_prompt:,} / completion={judge_completion:,}",
        f"- vlm_cache_files: {cache_count}",
        f"- vlm_imgcache_files: {img_count}",
        "",
        "## Domain Scores",
        "",
        domain_table,
        "",
        "## Type Scores",
        "",
        type_table,
        "",
        "## Reproduction Notes",
        "",
        "- `answers.csv` and `judged.csv` are the primary run outputs.",
        "- The evaluation target is the repository-root `rag_evaluation_master.csv`, obtained from the Hugging Face dataset release.",
        "- `vlm_cache/` contains the Markdown cache variant used by this run.",
        "- `vlm_imgcache/` contains image-level VLM responses for VLM runs; no-VLM runs include a README marker.",
    ]
    if errors:
        lines.extend(["", "## Answer Errors", "", "| idx | error |", "|---|---|"])
        lines.extend(f"| {r.get('idx')} | {r.get('error', '').replace('|', '/')} |" for r in errors)

    (run_dir / "analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", choices=sorted(RUNS))
    ap.add_argument("--mode", choices=("vlm", "novlm"), help="override run cache mode")
    ap.add_argument("--dataset-name", help="override Dify dataset name written to analysis.md")
    ap.add_argument("--generation-model", help="override generation model written to analysis.md")
    ap.add_argument("--judge-model", help="override judge model written to analysis.md")
    args = ap.parse_args()

    cfg = dict(RUNS[args.run])
    if args.mode:
        cfg["mode"] = args.mode
    if args.dataset_name:
        cfg["dataset"] = args.dataset_name
    if args.generation_model:
        cfg["generation_model"] = args.generation_model
    if args.judge_model:
        cfg["judge_model"] = args.judge_model

    run_dir = RESULTS / args.run
    run_dir.mkdir(parents=True, exist_ok=True)

    cache_count = copy_selected_cache(ROOT / "vlm_cache", run_dir / "vlm_cache", cfg["mode"])
    img_count = copy_img_cache(ROOT / "vlm_imgcache", run_dir / "vlm_imgcache", cfg["mode"])
    write_analysis(args.run, cfg, run_dir, cache_count, img_count)
    print(f"finalized {run_dir}")


if __name__ == "__main__":
    main()
