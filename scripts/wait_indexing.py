#!/usr/bin/env python3
# =============================================================
# wait_indexing.py
#   01_upload_documents_vlm.py の投入後に、Dify ナレッジの
#   インデキシング完了をポーリングして待機する。
#
#   - documents API の indexing_status を監視し、対象 PDF 全件が
#     completed になるまで待つ(既定: documents/ の全65本)。
#   - status=error / 未投入(missing) の文書は「削除→同名で再投入」して復旧する。
#     再投入は文書ごとに最大 --max-retry 回まで(既定2)。無限ループしない。
#   - 全件 completed なら exit 0。リトライ上限後も残れば exit 1(タイムアウトも 1)。
#
#   01 と同じ HTTP/VLM ロジックを使うため、01 をモジュールとして読み込む。
#   再投入時の Markdown は vlm_cache を再利用するので VLM は呼び直さない。
#
# 使い方:
#   export DIFY_KNOWLEDGE_API_KEY=dataset-xxxx
#   python3 wait_indexing.py
#   python3 wait_indexing.py --timeout 3600 --interval 10 --max-retry 2
# =============================================================
import sys
import time
import argparse
import importlib.util
import urllib.parse
from pathlib import Path

# 01_upload_documents_vlm.py はファイル名が数字始まりで import 不可なので動的読込する。
_spec = importlib.util.spec_from_file_location(
    "upload_vlm", Path(__file__).resolve().parent / "01_upload_documents_vlm.py")
up = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(up)

DONE = "completed"
# completed / error / missing 以外は「処理中」とみなす(waiting/parsing/splitting/indexing 等)。


def find_dataset_id() -> str:
    page = 1
    while True:
        q = urllib.parse.urlencode({"page": page, "limit": 100})
        data = up.http_json(f"{up.BASE_URL}/v1/datasets?{q}", headers=up.dify_headers(), timeout=30)
        for ds in data.get("data", []):
            if ds["name"] == up.DATASET_NAME:
                return ds["id"]
        if not data.get("has_more"):
            break
        page += 1
    up.die(f"ナレッジが見つかりません: {up.DATASET_NAME}(先に 01 を実行してください)")


def fetch_docs(ds_id: str) -> dict:
    """name -> {'id', 'status'} を返す。"""
    docs = {}
    page = 1
    while True:
        q = urllib.parse.urlencode({"page": page, "limit": 100})
        data = up.http_json(f"{up.BASE_URL}/v1/datasets/{ds_id}/documents?{q}",
                            headers=up.dify_headers(), timeout=30)
        for d in data.get("data", []):
            docs[d["name"]] = {"id": d.get("id"), "status": d.get("indexing_status")}
        if not data.get("has_more"):
            return docs
        page += 1


def reupload(ds_id: str, name: str, pdf_path: Path, rec: dict):
    """error/missing の文書を削除→同名で再投入する。Markdown は cache 再利用(VLM 再実行なし)。"""
    if rec and rec.get("id"):
        try:
            up.http_json(f"{up.BASE_URL}/v1/datasets/{ds_id}/documents/{rec['id']}",
                         headers=up.dify_headers(), method="DELETE", timeout=30)
        except Exception as e:
            print(f"    削除失敗(無視して再投入を試みる): {name}: {e}")
    try:
        md = up.get_markdown(pdf_path, page_images=False, use_cache=True)
        up.push_to_dify(ds_id, name, md)
        print(f"    再投入: {name}")
    except Exception as e:
        print(f"    再投入失敗: {name}: {e}")  # 失敗もリトライ消費として扱い、無限ループを防ぐ


def main():
    ap = argparse.ArgumentParser(description="Dify ナレッジのインデキシング完了を待つ(error は再投入)")
    ap.add_argument("pdfs", nargs="*", help="対象PDF(省略時は documents/ 全件)。ファイル名のみ可")
    ap.add_argument("--interval", type=int, default=10, help="ポーリング間隔(秒)")
    ap.add_argument("--timeout", type=int, default=3600, help="全体タイムアウト(秒)")
    ap.add_argument("--max-retry", type=int, default=2, help="文書ごとの再投入の上限回数")
    args = ap.parse_args()

    if not up.API_KEY:
        up.die("環境変数 DIFY_KNOWLEDGE_API_KEY を設定してください")

    pdfs = up.select_pdfs(args.pdfs)
    expected = {p.name: p for p in pdfs}
    ds_id = find_dataset_id()
    print(f"待機開始: ナレッジ={up.DATASET_NAME}({ds_id}) / 対象 {len(expected)} 件 / "
          f"interval={args.interval}s timeout={args.timeout}s max_retry={args.max_retry}")

    retries = {}            # name -> 再投入回数
    deadline = time.time() + args.timeout
    t0 = time.time()

    while True:
        docs = fetch_docs(ds_id)
        status_of = lambda n: docs.get(n, {}).get("status") or "missing"
        done = [n for n in expected if status_of(n) == DONE]
        bad = [n for n in expected if status_of(n) in ("error", "missing")]
        pending = [n for n in expected if n not in done and n not in bad]

        print(f"[{int(time.time() - t0):5d}s] 完了 {len(done)}/{len(expected)} / "
              f"処理中 {len(pending)} / 要復旧 {len(bad)}")

        if len(done) == len(expected):
            print("全文書のインデキシング完了。")
            return

        # リトライ予算が残る error/missing を再投入(削除→再投入)
        retriable = [n for n in bad if retries.get(n, 0) < args.max_retry]
        for n in retriable:
            reupload(ds_id, n, expected[n], docs.get(n))
            retries[n] = retries.get(n, 0) + 1

        # 復旧手段が尽きた(リトライ上限超過)かつ処理中も無ければ失敗確定
        exhausted = [n for n in bad if retries.get(n, 0) >= args.max_retry]
        if exhausted and not pending and not retriable:
            up.die(f"再投入 {args.max_retry} 回後もインデキシング失敗: {exhausted}")

        if time.time() > deadline:
            up.die(f"タイムアウト({args.timeout}s)。未完了: 処理中{len(pending)} 要復旧{len(bad)}")

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
