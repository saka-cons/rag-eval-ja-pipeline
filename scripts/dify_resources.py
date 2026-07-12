#!/usr/bin/env python3
"""Manage Dify datasets/apps for the r1-r4 reproduction workflow."""
from __future__ import annotations

import argparse
import csv
import json
import os
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = ROOT / "dify" / "dify_app_template.yml"

BASE_URL = os.environ.get("DIFY_BASE_URL", "http://localhost").rstrip("/")
KNOWLEDGE_API_KEY = os.environ.get("DIFY_KNOWLEDGE_API_KEY", "")
CONSOLE_TOKEN = os.environ.get("DIFY_CONSOLE_ACCESS_TOKEN") or os.environ.get("DIFY_ADMIN_API_KEY", "")
CONSOLE_CSRF_TOKEN = os.environ.get("DIFY_CONSOLE_CSRF_TOKEN", "")
EMBEDDING_MODEL = os.environ.get("DIFY_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B-GGUF")
EMBEDDING_PROVIDER = os.environ.get("DIFY_EMBEDDING_PROVIDER", "stvlynn/lmstudio/lmstudio")


def load_env(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.split("#", 1)[0].strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def refresh_env() -> None:
    global BASE_URL, KNOWLEDGE_API_KEY, CONSOLE_TOKEN, CONSOLE_CSRF_TOKEN, EMBEDDING_MODEL, EMBEDDING_PROVIDER
    load_env()
    BASE_URL = os.environ.get("DIFY_BASE_URL", "http://localhost").rstrip("/")
    KNOWLEDGE_API_KEY = os.environ.get("DIFY_KNOWLEDGE_API_KEY", "")
    CONSOLE_TOKEN = os.environ.get("DIFY_CONSOLE_ACCESS_TOKEN") or os.environ.get("DIFY_ADMIN_API_KEY", "")
    CONSOLE_CSRF_TOKEN = os.environ.get("DIFY_CONSOLE_CSRF_TOKEN", "")
    EMBEDDING_MODEL = os.environ.get("DIFY_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B-GGUF")
    EMBEDDING_PROVIDER = os.environ.get("DIFY_EMBEDDING_PROVIDER", "stvlynn/lmstudio/lmstudio")


def die(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def http_json(url: str, *, payload=None, headers=None, method="GET", timeout=120) -> dict:
    req_headers = dict(headers or {})
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = res.read().decode("utf-8").strip()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"{method} {url} failed: HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"{method} {url} failed: {e.reason}") from e


def knowledge_headers() -> dict:
    if not KNOWLEDGE_API_KEY:
        die("DIFY_KNOWLEDGE_API_KEY is required")
    return {"Authorization": f"Bearer {KNOWLEDGE_API_KEY}"}


def console_headers() -> dict:
    if not CONSOLE_TOKEN:
        die("DIFY_ADMIN_API_KEY or DIFY_CONSOLE_ACCESS_TOKEN is required")
    headers = {"Authorization": f"Bearer {CONSOLE_TOKEN}"}
    if CONSOLE_CSRF_TOKEN:
        headers["X-CSRF-Token"] = CONSOLE_CSRF_TOKEN
        headers["Cookie"] = f"csrf_token={CONSOLE_CSRF_TOKEN}"
    return headers


def mask_token(token: str) -> str:
    if len(token) <= 12:
        return "***"
    return f"{token[:4]}...{token[-6:]}"


def list_datasets() -> list[dict]:
    page = 1
    out: list[dict] = []
    while True:
        q = urllib.parse.urlencode({"page": page, "limit": 100, "include_all": "true"})
        data = http_json(f"{BASE_URL}/v1/datasets?{q}", headers=knowledge_headers(), timeout=30)
        out.extend(data.get("data", []))
        if not data.get("has_more"):
            return out
        page += 1


def dataset_by_name(name: str) -> dict:
    for ds in list_datasets():
        if ds.get("name") == name:
            return ds
    die(f"Dify dataset not found: {name}")


def list_documents(dataset_id: str) -> list[dict]:
    page = 1
    out: list[dict] = []
    while True:
        q = urllib.parse.urlencode({"page": page, "limit": 100})
        data = http_json(
            f"{BASE_URL}/v1/datasets/{dataset_id}/documents?{q}",
            headers=knowledge_headers(),
            timeout=30,
        )
        out.extend(data.get("data", []))
        if not data.get("has_more"):
            return out
        page += 1


def dataset_summary(name: str) -> dict:
    ds = dataset_by_name(name)
    docs = list_documents(ds["id"])
    return {
        "dataset": {
            "id": ds.get("id"),
            "name": ds.get("name"),
            "embedding_model": ds.get("embedding_model"),
            "embedding_model_provider": ds.get("embedding_model_provider"),
            "embedding_available": ds.get("embedding_available"),
            "indexing_technique": ds.get("indexing_technique"),
        },
        "document_count": len(docs),
        "status_counts": dict(Counter(d.get("indexing_status") or "unknown" for d in docs)),
        "tokens_total": sum(int(d.get("tokens") or 0) for d in docs),
        "word_count_total": sum(int(d.get("word_count") or 0) for d in docs),
        "documents": [
            {
                "id": d.get("id"),
                "name": d.get("name"),
                "indexing_status": d.get("indexing_status"),
                "tokens": d.get("tokens"),
                "word_count": d.get("word_count"),
            }
            for d in docs
        ],
    }


def write_json(path: Path | None, obj: dict) -> None:
    if not path:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def first_master_query(master: Path) -> str:
    with master.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            query = (row.get("question_new") or row.get("question") or "").strip()
            if query:
                return query[:250]
    die(f"no query found in {master}")


def retrieve_dataset(name: str, query: str) -> dict:
    ds = dataset_by_name(name)
    payload = {"query": query}
    return http_json(
        f"{BASE_URL}/v1/datasets/{ds['id']}/retrieve",
        payload=payload,
        headers=knowledge_headers(),
        method="POST",
        timeout=120,
    )


def validate_dataset(name: str, query: str) -> dict:
    summary = dataset_summary(name)
    retrieve = retrieve_dataset(name, query)
    records = retrieve.get("records", [])
    result = {
        "dataset_summary": {
            k: v for k, v in summary.items() if k != "documents"
        },
        "probe_query": query,
        "retrieve_record_count": len(records),
        "retrieve_sample": records[:3],
        "ok": len(records) > 0,
    }
    status_counts = summary.get("status_counts", {})
    if status_counts.get("completed", 0) != summary.get("document_count", 0):
        result["ok"] = False
    if summary.get("document_count", 0) == 0:
        result["ok"] = False
    if not result["ok"]:
        raise RuntimeError(f"Dify dataset validation failed for {name}: {json.dumps(result, ensure_ascii=False)[:800]}")
    return result


def list_apps(name: str | None = None) -> list[dict]:
    page = 1
    out: list[dict] = []
    while True:
        params = {"page": page, "limit": 100, "mode": "all"}
        if name:
            params["name"] = name
        q = urllib.parse.urlencode(params)
        data = http_json(f"{BASE_URL}/console/api/apps?{q}", headers=console_headers(), timeout=30)
        out.extend(data.get("data") or data.get("items") or [])
        if not data.get("has_more"):
            return out
        page += 1


def app_by_name(name: str) -> dict | None:
    for app in list_apps(name):
        if app.get("name") == name:
            return app
    return None


def rewrite_template(template: Path, *, app_name: str, dataset_id: str, generation_model: str) -> str:
    text = template.read_text(encoding="utf-8")
    text = text.replace("REPLACE_WITH_DIFY_DATASET_ID", dataset_id)
    text = text.replace("name: 知識リトリーバル + チャットボット", f"name: {app_name}")
    text = text.replace("name: qwen/qwen3.6-35b-a3b", f"name: {generation_model}")
    return text


def import_app(yaml_content: str, app_name: str, app_id: str | None = None) -> dict:
    payload = {
        "mode": "yaml-content",
        "yaml_content": yaml_content,
        "name": app_name,
        "description": "RAG Eval JA r1-r4 automated reproduction app",
        "icon_type": "emoji",
        "icon": "🤖",
        "icon_background": "#FFEAD5",
    }
    if app_id:
        payload["app_id"] = app_id
    result = http_json(
        f"{BASE_URL}/console/api/apps/imports",
        payload=payload,
        headers=console_headers(),
        method="POST",
        timeout=120,
    )
    if result.get("status") == "pending":
        result = http_json(
            f"{BASE_URL}/console/api/apps/imports/{result['id']}/confirm",
            headers=console_headers(),
            method="POST",
            timeout=120,
        )
    if result.get("status") not in {"completed", "completed-with-warnings"}:
        die(f"app import failed: {json.dumps(result, ensure_ascii=False)}")
    return result


def publish_app(app_id: str) -> None:
    http_json(
        f"{BASE_URL}/console/api/apps/{app_id}/workflows/publish",
        payload={"marked_name": "", "marked_comment": ""},
        headers=console_headers(),
        method="POST",
        timeout=120,
    )
    http_json(
        f"{BASE_URL}/console/api/apps/{app_id}/api-enable",
        payload={"enable_api": True},
        headers=console_headers(),
        method="POST",
        timeout=30,
    )


def get_or_create_app_key(app_id: str) -> dict:
    keys = http_json(
        f"{BASE_URL}/console/api/apps/{app_id}/api-keys",
        headers=console_headers(),
        timeout=30,
    ).get("data", [])
    if keys:
        return keys[0]
    return http_json(
        f"{BASE_URL}/console/api/apps/{app_id}/api-keys",
        headers=console_headers(),
        method="POST",
        timeout=30,
    )


def append_env(path: Path, name: str, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"export {name}='{value}'\n")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def ensure_app(args) -> dict:
    ds = dataset_by_name(args.dataset_name)
    app_name = args.app_name or f"RAG Eval JA {args.run} {args.run_slug}"
    existing = app_by_name(app_name)
    yaml_content = rewrite_template(
        args.template,
        app_name=app_name,
        dataset_id=ds["id"],
        generation_model=args.generation_model,
    )
    imported = import_app(yaml_content, app_name, existing.get("id") if existing else None)
    app_id = imported["app_id"]
    publish_app(app_id)
    api_key = get_or_create_app_key(app_id)
    token = api_key.get("token") or ""
    if not token:
        die(f"could not obtain app API key for {app_name}")
    if args.key_env:
        append_env(args.key_env, args.env_name or f"DIFY_APP_API_KEY_{args.run.upper()}", token)
    result = {
        "run": args.run,
        "app_name": app_name,
        "app_id": app_id,
        "app_mode": imported.get("app_mode"),
        "dataset_name": args.dataset_name,
        "dataset_id": ds["id"],
        "generation_model": args.generation_model,
        "api_key_id": api_key.get("id"),
        "api_key_token_masked": mask_token(token),
        "import_status": imported.get("status"),
    }
    return result


def main() -> None:
    refresh_env()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("dataset-id")
    p.add_argument("--name", required=True)

    p = sub.add_parser("dataset-summary")
    p.add_argument("--name", required=True)
    p.add_argument("--out", type=Path)

    p = sub.add_parser("validate-dataset")
    p.add_argument("--name", required=True)
    p.add_argument("--query")
    p.add_argument("--query-from-master", type=Path, default=ROOT / "rag_evaluation_master.csv")
    p.add_argument("--out", type=Path)

    p = sub.add_parser("ensure-app")
    p.add_argument("--run", required=True, choices=("r1", "r2", "r3", "r4"))
    p.add_argument("--run-slug", required=True)
    p.add_argument("--dataset-name", required=True)
    p.add_argument("--generation-model", required=True)
    p.add_argument("--app-name")
    p.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    p.add_argument("--out", type=Path)
    p.add_argument("--key-env", type=Path)
    p.add_argument("--env-name")

    args = ap.parse_args()
    try:
        if args.cmd == "dataset-id":
            print(dataset_by_name(args.name)["id"])
        elif args.cmd == "dataset-summary":
            write_json(args.out, dataset_summary(args.name))
        elif args.cmd == "validate-dataset":
            query = args.query or first_master_query(args.query_from_master)
            write_json(args.out, validate_dataset(args.name, query))
        elif args.cmd == "ensure-app":
            result = ensure_app(args)
            write_json(args.out, result)
            print(f"ensured {result['run']} app={result['app_id']} dataset={result['dataset_id']}")
        else:
            raise AssertionError(args.cmd)
    except Exception as e:
        die(str(e))


if __name__ == "__main__":
    main()
