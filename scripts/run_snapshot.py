#!/usr/bin/env python3
"""Create and verify local snapshots for r1-r4 reproduction runs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
SNAPSHOTS = RESULTS / "_snapshots"

RUNS = ("r1", "r2", "r3", "r4")
RUN_FILES = ("answers.csv", "judged.csv", "report.md", "analysis.md")
ANALYSIS_FILES = (
    "analysis_r1_r4_current.md",
    "analysis_r1_r4_answer_traits.md",
    "r1_r4_answer_traits_summary.csv",
    "r1_r4_answer_traits_by_type.csv",
    "r1_r4_answer_traits_by_ox.csv",
    "r1_r4_answer_traits_contrasts.csv",
    "r1_r4_answer_traits_per_question.csv",
)


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception:
        return ""


def count_csv_rows(path: Path) -> int | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def copy_if_exists(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


def make_manifest(run_id: str, run_slug: str, snapshot: Path) -> dict:
    return {
        "run_id": run_id,
        "run_slug": run_slug,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "repo": str(ROOT),
        "head": git_value("rev-parse", "HEAD"),
        "head_short": git_value("rev-parse", "--short", "HEAD"),
        "old_commit": "c6977cebf639417536c360eb9ae3637885a5cff0",
        "master_csv_sha256": sha256(ROOT / "rag_evaluation_master.csv"),
        "documents_manifest_sha256": sha256(ROOT / "repro" / "documents_manifest.csv"),
        "documents_checksums_sha256": sha256(ROOT / "repro" / "documents_checksums.sha256"),
        "snapshot_dir": str(snapshot),
    }


def cmd_create(args) -> None:
    snapshot = SNAPSHOTS / args.run_id
    snapshot.mkdir(parents=True, exist_ok=True)
    manifest = make_manifest(args.run_id, args.run_slug, snapshot)
    (snapshot / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    copy_if_exists(ROOT / "rag_evaluation_master.csv", snapshot / "rag_evaluation_master.csv")
    copy_if_exists(ROOT / "repro" / "documents_manifest.csv", snapshot / "repro" / "documents_manifest.csv")
    copy_if_exists(ROOT / "repro" / "documents_checksums.sha256", snapshot / "repro" / "documents_checksums.sha256")
    copy_if_exists(ROOT / "repro" / "download_sources.csv", snapshot / "repro" / "download_sources.csv")
    print(snapshot)


def cmd_capture(args) -> None:
    snapshot = SNAPSHOTS / args.run_id
    snapshot.mkdir(parents=True, exist_ok=True)
    for run in RUNS:
        copy_if_exists(RESULTS / run, snapshot / "results" / run)
    copy_if_exists(ROOT / "analysis", snapshot / "analysis")
    copy_if_exists(RESULTS / "vlm_usage.csv", snapshot / "vlm_usage.csv")
    print(f"captured {snapshot}")


def verify() -> dict:
    missing: list[str] = []
    row_counts: dict[str, dict[str, int | None]] = {}
    for run in RUNS:
        row_counts[run] = {}
        for name in RUN_FILES:
            path = RESULTS / run / name
            if not path.exists():
                missing.append(str(path.relative_to(ROOT)))
            if name.endswith(".csv"):
                row_counts[run][name] = count_csv_rows(path)
        for dirname in ("vlm_cache", "vlm_imgcache"):
            path = RESULTS / run / dirname
            if not path.exists():
                missing.append(str(path.relative_to(ROOT)))
        if not (RESULTS / run / "rag_evaluation_master.csv").exists():
            missing.append(str((RESULTS / run / "rag_evaluation_master.csv").relative_to(ROOT)))

    for name in ANALYSIS_FILES:
        path = ROOT / "analysis" / name
        if not path.exists():
            missing.append(str(path.relative_to(ROOT)))

    wrong_counts = {
        f"{run}/{name}": count
        for run, counts in row_counts.items()
        for name, count in counts.items()
        if count != 300
    }
    return {
        "ok": not missing and not wrong_counts,
        "missing": missing,
        "row_counts": row_counts,
        "wrong_counts": wrong_counts,
    }


def cmd_verify(args) -> None:
    result = verify()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("create")
    p.add_argument("--run-id", required=True)
    p.add_argument("--run-slug", required=True)

    p = sub.add_parser("capture")
    p.add_argument("--run-id", required=True)

    p = sub.add_parser("verify")
    p.add_argument("--out", type=Path)

    args = ap.parse_args()
    if args.cmd == "create":
        cmd_create(args)
    elif args.cmd == "capture":
        cmd_capture(args)
    elif args.cmd == "verify":
        cmd_verify(args)


if __name__ == "__main__":
    main()
