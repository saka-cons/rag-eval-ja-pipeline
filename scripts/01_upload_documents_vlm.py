#!/usr/bin/env python3
# =============================================================
# 01_upload_documents_vlm.py
#   01_upload_documents.py の VLM 版。
#
#   通常版(create-by-file)は Dify が PDF からテキストしか抽出せず、
#   図表・グラフ・表の情報が embedding に乗らない。
#   本スクリプトは取込前に Qwen3-VL(LM Studio)で図表をテキスト化し、
#   本文と結合した Markdown を create-by-text で投入する。
#
# 処理フロー(PDF 1本ごと):
#   1. ページの本文テキストを抽出 (PyMuPDF)
#   2. ページ内の埋め込み画像を抽出(--page-images 時はページ全体を画像化)
#   3. 小さすぎる画像(アイコン/罫線)はスキップ
#   4. 各画像を LM Studio の Qwen3-VL でテキスト化
#   5. 本文 + [図表の説明] を結合した Markdown を組み立て
#   6. 1 PDF = 1 ドキュメントとして Dify Knowledge API(create-by-text)に投入
#
# 依存: PyMuPDF(import fitz) のみ。HTTP は標準ライブラリ urllib で実装。
#       → PyMuPDF が入った Python 環境で動く(requests 不要)。
#
# 使い方:
#   # テスト用 documents/ 配下の PDF で VLM 抽出だけ確認(Dify 投入なし / LM Studio 必須)
#   python 01_upload_documents_vlm.py --sample --dry-run
#
#   # テスト用 documents/ 配下の PDF を実際に Dify へテスト投入(要 DIFY_KNOWLEDGE_API_KEY)
#   python 01_upload_documents_vlm.py --sample
#
#   # 1ドキュメントだけ VLM 抽出を確認(Dify には投入しない / LM Studio 必須)
#   python 01_upload_documents_vlm.py --limit 1 --dry-run
#
#   # 特定の1ファイルだけ実投入
#   export DIFY_KNOWLEDGE_API_KEY=dataset-xxxx
#   python 01_upload_documents_vlm.py 000040369.pdf
#
#   # 全65本を投入
#   python 01_upload_documents_vlm.py
#
#   # ベクター図/スキャンPDF向け: ページ全体を画像化して VLM に渡す
#   python 01_upload_documents_vlm.py --limit 1 --dry-run --page-images
# =============================================================
import os
import re
import csv
import sys
import json
import time
import base64
import hashlib
import argparse
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

import fitz  # PyMuPDF

# ---- Dify 設定(01_upload_documents.py と同じ環境変数) -------
BASE_URL = os.environ.get("DIFY_BASE_URL", "http://localhost").rstrip("/")
API_KEY = os.environ.get("DIFY_KNOWLEDGE_API_KEY")
# 新実験用の独立ナレッジ名(既存の取込結果と混ざらないよう専用名にする)
DATASET_NAME = os.environ.get("DIFY_DATASET_NAME", "RAG-Eval-JA-master")
DOCS_DIR = Path(__file__).resolve().parent.parent / "documents"
# VLM 抽出結果の Markdown キャッシュ(再実行で VLM を呼び直さない)
CACHE_DIR = Path(os.environ.get("VLM_CACHE_DIR", Path(__file__).resolve().parent.parent / "vlm_cache"))
# 画像単位の VLM 応答キャッシュ(内容ハッシュ key)。--refresh で .md を作り直しても
# 同一画像の VLM 再実行を避ける。VLM は temperature=0/seed 固定で決定論的なので副作用なし。
IMG_CACHE_DIR = Path(os.environ.get("VLM_IMG_CACHE_DIR", Path(__file__).resolve().parent.parent / "vlm_imgcache"))
# VLM の実呼び出し(キャッシュミス時)の token usage を追記する CSV。
# cache hit は API を叩かないため記録されない。
USAGE_LOG = Path(os.environ.get("VLM_USAGE_LOG", Path(__file__).resolve().parent.parent / "results" / "vlm_usage.csv"))
_VLM_TOK = {"calls": 0, "prompt": 0, "completion": 0}
# 疎通テスト用PDF(本文+棒グラフ+仕様表)。--sample で参照する
SAMPLE_PDF = Path(__file__).resolve().parent.parent.parent / "pymupdf" / "documents/ 配下の PDF"

# ---- LM Studio (VLM) 設定 -----------------------------------
LMSTUDIO_API = os.environ.get("LMSTUDIO_API", "http://localhost:1234").rstrip("/")
VLM_MODEL = os.environ.get("VLM_MODEL", "qwen/qwen3-vl-8b")
LM_TOKEN = os.environ.get("LM_API_TOKEN", "")

# ---- 埋め込みモデル設定(Dify 上の表記に合わせる) -----------
# ★API で自動作成したナレッジは retrieval_model.vector_setting が空のまま作られ、
#  検索でクエリをベクトル化できず常に0件になる。作成時に必ず埋めること。
#  値はテキスト版ナレッジ(RAG-Eval-JA)で確認した実値が既定。
EMBEDDING_MODEL = os.environ.get("DIFY_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B-GGUF")
EMBEDDING_PROVIDER = os.environ.get("DIFY_EMBEDDING_PROVIDER", "stvlynn/lmstudio/lmstudio")
RETRIEVAL_MODEL = {
    "search_method": "hybrid_search",
    "reranking_enable": False,
    "reranking_mode": "weighted_score",
    "reranking_model": {"reranking_provider_name": "", "reranking_model_name": ""},
    "weights": {
        "weight_type": "customized",
        "keyword_setting": {"keyword_weight": 0.3},
        "vector_setting": {
            "vector_weight": 0.7,
            "embedding_model_name": EMBEDDING_MODEL,
            "embedding_provider_name": EMBEDDING_PROVIDER,
        },
    },
    "top_k": 10,
    "score_threshold_enabled": False,
    "score_threshold": 0.0,
}

# 図表とみなす最小サイズ(これ未満はアイコン等として無視)
MIN_IMG_W = 120
MIN_IMG_H = 120

# チャンク設定(01_upload_documents.py と同一にして条件を揃える)
PROCESS_RULE = {
    "indexing_technique": "high_quality",
    "process_rule": {
        "mode": "custom",
        "rules": {
            "pre_processing_rules": [
                {"id": "remove_extra_spaces", "enabled": True},
                {"id": "remove_urls_emails", "enabled": False},
            ],
            "segmentation": {"separator": "\n\n", "max_tokens": 1024, "chunk_overlap": 100},
        },
    },
}

VLM_PROMPT = (
    "You are a document image extractor for a RAG knowledge base. "
    "Describe this image as searchable plain text in the document's original "
    "language (Japanese if the figure is Japanese). If it contains a chart, "
    "report every axis label and data value. If it contains a table, "
    "transcribe all rows and columns. If it is a diagram, describe its "
    "structure and labels. Be precise and complete. Output only the extracted text."
)


def die(msg: str):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


# ---- HTTP ヘルパ(urllib) -----------------------------------
def http_json(url, payload=None, headers=None, method="GET", timeout=300):
    headers = dict(headers or {})
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8").strip()
        return json.loads(body) if body else {}  # DELETE等は 204 空ボディを返す


def dify_headers():
    return {"Authorization": f"Bearer {API_KEY}"}


# ---- Dify: ナレッジ取得/作成・既存ドキュメント -------------
def get_or_create_dataset() -> str:
    page = 1
    while True:
        q = urllib.parse.urlencode({"page": page, "limit": 100})
        data = http_json(f"{BASE_URL}/v1/datasets?{q}", headers=dify_headers(), timeout=30)
        for ds in data.get("data", []):
            if ds["name"] == DATASET_NAME:
                print(f"既存ナレッジを使用: {DATASET_NAME} ({ds['id']})")
                ensure_embedding_config(ds["id"])  # 埋め込み未紐付けの既存ナレッジを自己修復
                return ds["id"]
        if not data.get("has_more"):
            break
        page += 1
    res = http_json(f"{BASE_URL}/v1/datasets", payload={
        "name": DATASET_NAME,
        "permission": "only_me",
        "indexing_technique": "high_quality",
        "embedding_model": EMBEDDING_MODEL,
        "embedding_model_provider": EMBEDDING_PROVIDER,
        "retrieval_model": RETRIEVAL_MODEL,
    }, headers=dify_headers(), method="POST", timeout=30)
    print(f"ナレッジを新規作成: {DATASET_NAME} ({res['id']})")
    return res["id"]


def ensure_embedding_config(ds_id: str):
    """既存ナレッジの検索設定(retrieval_model)/embedding_model 表記を揃える。
    注意: 埋め込みモデル『無し』で作成されたナレッジはベクトルコレクションの
    紐付けが壊れており、ここで PATCH しても検索は復旧しない(作り直しが必要)。
    新規作成は get_or_create_dataset が最初から embedding_model 付きで作るので問題ない。"""
    try:
        http_json(f"{BASE_URL}/v1/datasets/{ds_id}", payload={
            "name": DATASET_NAME,
            "indexing_technique": "high_quality",
            "embedding_model": EMBEDDING_MODEL,
            "embedding_model_provider": EMBEDDING_PROVIDER,
            "retrieval_model": RETRIEVAL_MODEL,
        }, headers=dify_headers(), method="PATCH", timeout=30)
        sys.stderr.write(f"    embedding設定を確認/更新: {EMBEDDING_MODEL}\n")
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"    embedding設定の更新に失敗(無視可): {e.code}\n")


def delete_all_documents(ds_id: str):
    """ナレッジ内の全ドキュメントを削除する(--purge 用)。"""
    n = 0
    while True:
        q = urllib.parse.urlencode({"page": 1, "limit": 100})
        data = http_json(f"{BASE_URL}/v1/datasets/{ds_id}/documents?{q}",
                         headers=dify_headers(), timeout=30)
        docs = data.get("data", [])
        if not docs:
            break
        for d in docs:
            http_json(f"{BASE_URL}/v1/datasets/{ds_id}/documents/{d['id']}",
                      headers=dify_headers(), method="DELETE", timeout=30)
            n += 1
        sys.stderr.write(f"    削除済み {n} 件...\n")
    print(f"既存ドキュメントを全削除: {n} 件")


def existing_documents(ds_id: str) -> set:
    names = set()
    page = 1
    while True:
        q = urllib.parse.urlencode({"page": page, "limit": 100})
        data = http_json(f"{BASE_URL}/v1/datasets/{ds_id}/documents?{q}",
                         headers=dify_headers(), timeout=30)
        names.update(d["name"] for d in data.get("data", []))
        if not data.get("has_more"):
            return names
        page += 1


def embedding_usage():
    """Dify ナレッジ内の全ドキュメントの embedding トークン(取込/indexing 時に消費)を集計する。
    embedding は Dify 内部でチャンクごとに実行されるためスクリプトの応答には出ない。
    documents API の tokens フィールド(chunk overlap 込みの実埋め込み量)を合算して得る。
    検索時のクエリ埋め込みは別計上(設問300件を tokenize すれば概算)。"""
    if not API_KEY:
        die("環境変数 DIFY_KNOWLEDGE_API_KEY を設定してください")
    ds_id, page = None, 1
    while True:
        q = urllib.parse.urlencode({"page": page, "limit": 100})
        data = http_json(f"{BASE_URL}/v1/datasets?{q}", headers=dify_headers(), timeout=30)
        for ds in data.get("data", []):
            if ds["name"] == DATASET_NAME:
                ds_id = ds["id"]
                break
        if ds_id or not data.get("has_more"):
            break
        page += 1
    if not ds_id:
        die(f"ナレッジが見つかりません: {DATASET_NAME}")

    tot_tok = tot_words = n = 0
    page = 1
    while True:
        q = urllib.parse.urlencode({"page": page, "limit": 100})
        data = http_json(f"{BASE_URL}/v1/datasets/{ds_id}/documents?{q}",
                         headers=dify_headers(), timeout=30)
        for d in data.get("data", []):
            tot_tok += int(d.get("tokens") or 0)
            tot_words += int(d.get("word_count") or 0)
            n += 1
        if not data.get("has_more"):
            break
        page += 1

    print(f"ナレッジ: {DATASET_NAME} ({ds_id})")
    print(f"ドキュメント数: {n}")
    print(f"embedding トークン合計(取込時 / chunk overlap 込み): {tot_tok:,}")
    print(f"word_count 合計: {tot_words:,}")
    print("※ Dify 側の集計値。検索時のクエリ埋め込みは別(設問の tokenize で概算)。")


def push_to_dify(ds_id: str, name: str, text: str):
    url = f"{BASE_URL}/v1/datasets/{ds_id}/document/create-by-text"
    payload = {"name": name, "text": text, **PROCESS_RULE}
    return http_json(url, payload=payload, headers=dify_headers(), method="POST", timeout=120)


# ---- VLM: 画像 → テキスト -----------------------------------
def _log_vlm_usage(key: str, usage: dict):
    """VLM の実呼び出し1件分の token usage を vlm_usage.csv に追記し、合計に加算する。"""
    if not usage:
        return
    _VLM_TOK["calls"] += 1
    _VLM_TOK["prompt"] += int(usage.get("prompt_tokens") or 0)
    _VLM_TOK["completion"] += int(usage.get("completion_tokens") or 0)
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not USAGE_LOG.exists()
    with open(USAGE_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["key", "model", "prompt_tokens", "completion_tokens", "total_tokens"])
        w.writerow([key, VLM_MODEL, usage.get("prompt_tokens", ""),
                    usage.get("completion_tokens", ""), usage.get("total_tokens", "")])


def vlm_describe_image(img_bytes, mime="image/png"):
    # 画像内容+プロンプト+モデルで決まる key。プロンプトを変えれば自動で別keyになる。
    key = hashlib.sha256(img_bytes + VLM_PROMPT.encode() + VLM_MODEL.encode()).hexdigest()
    cf = IMG_CACHE_DIR / f"{key}.txt"
    if cf.is_file():
        return cf.read_text(encoding="utf-8")

    b64 = base64.b64encode(img_bytes).decode("ascii")
    payload = {
        "model": VLM_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": VLM_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }],
        "temperature": 0,      # 再現性のため決定論化
        "seed": 1234,           # LM Studio: 同一入力で同一出力を狙う
        "max_tokens": 1200,
    }
    headers = {"Content-Type": "application/json"}
    if LM_TOKEN:
        headers["Authorization"] = f"Bearer {LM_TOKEN}"
    try:
        resp = http_json(f"{LMSTUDIO_API}/v1/chat/completions", payload=payload,
                         headers=headers, method="POST", timeout=300)
        text = resp["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        return f"[VLM ERROR {e.code}: {e.read().decode('utf-8')[:200]}]"
    except Exception as e:
        return f"[VLM ERROR: {e}]"
    _log_vlm_usage(key, resp.get("usage") or {})  # 実呼び出しのみ記録(cache hit は対象外)
    # 成功応答のみキャッシュ(エラーは次回再試行できるよう保存しない)
    IMG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cf.write_text(text, encoding="utf-8")
    return text


# 無情報な VLM 応答(エラー文 / 空白・装飾画像の「中身なし」説明)を検出する正規表現。
# 短い応答にのみ適用し、本物の説明文を巻き込まないようにする。
_EMPTY_VLM_RE = re.compile(
    r"entirely black|no visible text|no discernible|no extractable"
    r"|there is no (text|content|chart)|does not contain any"
    r"|no (searchable )?(plain )?text"
    r"|抽出可能なテキスト(は|が)?ありません"
    r"|テキスト(は|が)?(含まれて|抽出でき)",
    re.IGNORECASE,
)


def is_empty_vlm(text: str) -> bool:
    """VLM 応答が「エラー」または「中身なしの定型説明」かを判定する。
    True のものは Markdown に含めない(embedding ノイズになるため)。"""
    t = (text or "").strip()
    if not t or t.startswith("[VLM ERROR"):
        return True
    # 「中身なし」系は短文。長い実説明を誤除外しないよう 400 字未満に限定。
    return len(t) < 400 and bool(_EMPTY_VLM_RE.search(t))


# =============================================================
# Markdown 後処理(embedding ノイズ除去)
#   生成済み Markdown だけを対象にし、VLM を呼び直さずに精度を上げる:
#     (1) 装飾画像(風景/ロゴ/アイコン/イラスト等)の説明ブロックを削除
#     (2) VLM の degeneration(同一文/節の繰り返し)を VLM ブロック内で除去
#     (3) max_tokens を超える巨大段落を行/文境界で再分割(表の途中切れ対策)
#   既存キャッシュには --clean-cache で一括適用できる。
# =============================================================
# VLM が出力した図表ブロック([Figure n-m]/[Page n rendering])を抽出する。
# マーカー行から次のマーカー/ページ見出し/区切り線/末尾までを 1 ブロックとみなす。
_VLM_BLOCK_RE = re.compile(
    r"(?P<marker>\[(?:Figure \d+-\d+|Page \d+ rendering) \(extracted by vision model\)\])"
    r"(?P<body>.*?)"
    r"(?=\n*\[(?:Figure \d+-\d+|Page \d+ rendering) \(extracted by vision model\)\]"
    r"|\n## Page |\n\n---\n|\Z)",
    re.DOTALL,
)
# データ・手順・構造を含むブロックは画像型設問の答えになり得るので保護する。
_DECOR_PROTECT_RE = re.compile(
    r"表|グラフ|チャート|軸|ラベル|項目|データ|割合|推移|手順|ステップ|工程"
    r"|方法|フロー|構成|矢印|→|単位|合計|株式会社"
)
# 明確な装飾(短文)を装飾とみなすキーワード。
_DECOR_STRONG_RE = re.compile(r"風景|ロゴ|アイコン|キャラクター|装飾|模様|キービジュアル|雰囲気|挿絵|挿し絵|背景画像|笑顔")
_DECOR_WEAK_RE = re.compile(r"イラスト|写真|描かれて|描いた|描いて")
_DIGIT_RE = re.compile(r"\d")


def _is_decorative(desc: str) -> bool:
    """VLM 説明が『データを持たない装飾画像の描写』かを判定する。"""
    if _DECOR_PROTECT_RE.search(desc):
        return False                        # データ/手順を含む → 保護
    if len(_DIGIT_RE.findall(desc)) >= 5:
        return False                        # 数字が多い(データ図) → 保護
    if _DECOR_STRONG_RE.search(desc) and len(desc) < 500:
        return True
    if _DECOR_WEAK_RE.search(desc) and len(desc) < 200:
        return True
    return False


def _dedup_block_body(text: str) -> str:
    """VLM の degeneration(同一文/節の繰り返し)を 1 ブロック内で除去する。
    正規の繰り返しを壊さないよう、本文ではなく VLM ブロックの中身にだけ適用する。"""
    # 文(。区切り)単位: 直前と同一の連続重複 + 15字以上の文の再出現を除去
    out, seen, prev = [], set(), None
    for s in re.split(r"(?<=。)", text):
        k = s.strip()
        if not k:
            out.append(s)
            continue
        if k == prev:
            continue
        if len(k) >= 15 and k in seen:
            continue
        out.append(s)
        seen.add(k)
        prev = k
    text = "".join(out)
    # 節(、。区切り)単位: 15字以上の節の再出現を除去(文内ループ対策)
    out, seen = [], set()
    for s in re.split(r"(?<=[、。])", text):
        k = s.strip()
        if len(k) >= 15 and k in seen:
            continue
        out.append(s)
        if len(k) >= 15:
            seen.add(k)
    return "".join(out)


def _resegment_paragraphs(md: str, threshold=1000, budget=900):
    """max_tokens=1024 を超える巨大段落を行/文境界で再分割する。
    \\n\\n を挿入して Dify のセグメント区切りを増やし、表が途中で切れないようにする。
    戻り: (md, 再分割した段落数)。"""
    out, n = [], 0
    for seg in md.split("\n\n"):
        if len(seg) <= threshold:
            out.append(seg)
            continue
        units = []
        for line in seg.split("\n"):
            if len(line) <= budget:
                units.append(line)
            else:  # 1 行が長大: 。で更に割る
                buf = ""
                for s in re.split(r"(?<=。)", line):
                    if buf and len(buf) + len(s) > budget:
                        units.append(buf)
                        buf = s
                    else:
                        buf += s
                if buf:
                    units.append(buf)
        chunks, cur = [], ""
        for u in units:
            if cur and len(cur) + 1 + len(u) > budget:
                chunks.append(cur)
                cur = u
            else:
                cur = (cur + "\n" + u) if cur else u
        if cur:
            chunks.append(cur)
        if len(chunks) > 1:
            n += 1
        out.append("\n\n".join(chunks))
    return "\n\n".join(out), n


def clean_markdown(md: str):
    """embedding 前処理: 装飾ブロック削除 + 繰り返し除去 + 巨大段落の再分割。
    戻り: (cleaned_md, stats)。"""
    stats = {"decor_dropped": 0, "dedup_chars": 0, "reseg": 0}

    def _sub(m):
        marker, body = m.group("marker"), m.group("body")
        if _is_decorative(body.strip()):
            stats["decor_dropped"] += 1
            return ""  # マーカーごと削除(残る空行は後でまとめる)
        nb = _dedup_block_body(body)
        stats["dedup_chars"] += len(body) - len(nb)
        return marker + nb

    md = _VLM_BLOCK_RE.sub(_sub, md)
    md = re.sub(r"\n{3,}", "\n\n", md)          # 削除跡の余分な空行を畳む
    md, stats["reseg"] = _resegment_paragraphs(md)
    return md, stats


def clean_cache_files():
    """既存の vlm_cache/*.md を後処理して in-place で書き戻す(VLM 再実行なし)。"""
    files = sorted(CACHE_DIR.glob("*.md"))
    if not files:
        die(f"キャッシュが空です: {CACHE_DIR}")
    tot = {"decor": 0, "dedup": 0, "reseg": 0, "before": 0, "after": 0, "changed": 0}
    for f in files:
        before = f.read_text(encoding="utf-8")
        after, st = clean_markdown(before)
        changed = after != before
        if changed:
            f.write_text(after, encoding="utf-8")
            tot["changed"] += 1
        tot["decor"] += st["decor_dropped"]
        tot["dedup"] += st["dedup_chars"]
        tot["reseg"] += st["reseg"]
        tot["before"] += len(before)
        tot["after"] += len(after)
        if changed:
            print(f"  * {f.name}: 装飾-{st['decor_dropped']} "
                  f"重複-{st['dedup_chars']}字 再分割{st['reseg']}")
    print(f"\n完了: {tot['changed']}/{len(files)} ファイル更新 / "
          f"装飾削除 {tot['decor']}ブロック / 繰り返し除去 {tot['dedup']}字 / "
          f"再分割 {tot['reseg']}段落 / 総量 {tot['before']}->{tot['after']}字")
    print("→ 反映するには --purge で VLM ナレッジを作り直して再投入してください。")


def img_xref_to_png(doc, xref):
    """埋め込み画像を RGB(or グレースケール)PNG に正規化して返す。
    LM Studio が CMYK/特殊 colorspace・JPEG2000 等を base64 画像として拒否する
    ('url' field must be a base64 encoded image)問題を回避する。
    戻り: (png_bytes, width, height)。失敗時は (None, 0, 0)。"""
    try:
        pix = fitz.Pixmap(doc, xref)
    except Exception:
        return None, 0, 0
    try:
        # PNG で安全に送れるのは Gray(n=1)/RGB(n=3) のみ。CMYK やアルファ付きは変換。
        if pix.alpha or (pix.colorspace is not None and pix.colorspace.n not in (1, 3)):
            pix = fitz.Pixmap(fitz.csRGB, pix)
        return pix.tobytes("png"), pix.width, pix.height
    except Exception:
        return None, 0, 0


# ---- PDF → Markdown -----------------------------------------
def _is_expected_char(ch: str) -> bool:
    """日本語PDFの本文・表に正常に現れうる文字か。ToUnicode 破損による文字化けは
    フォントごとに様々なブロックへ誤マップされる(j-bunpu=ラテン拡張 / daikibo=シリア・
    ミャンマー・CJK拡張…)。化け先を列挙すると未知のフォントで漏れるため、逆に「正常な
    文字種」をホワイトリスト化し、残差(=想定外スクリプト)を化けとみなす。"""
    o = ord(ch)
    return (
        0x20 <= o <= 0x7E or        # ASCII 印字可能
        ch in "·×÷±°§" or           # 中点・乗除・度・節記号など本文記号
        0x0370 <= o <= 0x03FF or    # ギリシャ(数式変数 α β γ)
        0x2000 <= o <= 0x206F or    # 一般句読点(— – … 等)
        0x20A0 <= o <= 0x20CF or    # 通貨記号(¥ € 等)
        0x2100 <= o <= 0x23FF or    # 文字様/数字様/矢印/数学演算子/テクニカル(℃ № √ ≦)
        0x2460 <= o <= 0x27BF or    # 囲み英数/罫線/幾何図形/各種・装飾記号(① ㈱ ─ ■ ●)
        0x2E80 <= o <= 0x2FDF or    # CJK部首補助・康熙部首(⽉⽇=漢字と同義の異体)
        0x3000 <= o <= 0x33FF or    # CJK記号句読点・かな・CJK互換(℃ ㎡ ㎏ 等の単位)
        0x4E00 <= o <= 0x9FFF or    # CJK統合漢字
        0xE000 <= o <= 0xF8FF or    # 私用領域(装飾シンボルフォント)
        0xF900 <= o <= 0xFAFF or    # CJK互換漢字
        0xFE10 <= o <= 0xFE4F or    # 縦書き句読点・CJK互換形
        0xFF00 <= o <= 0xFFEF or    # 半角・全角
        0x1D400 <= o <= 0x1D7FF     # 数学英数字記号(数式 𝐷 𝛽 等)
    )


def _mojibake_ratio(text: str) -> float:
    """文字化けの割合。ToUnicode CMap が壊れた埋め込みフォントで get_text が誤コード
    ポイントを返すケースを検出する(NUL除去では落ちない)。正常な文字種(_is_expected_char)
    以外の比率を返す。空白は分母から除く。表・本文の双方の品質判定に使う。"""
    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return 0.0
    return sum(1 for ch in chars if not _is_expected_char(ch)) / len(chars)


def _is_good_table(t) -> bool:
    """find_tables の検出表が embedding に使える品質かを判定する。
    崩れた複雑表(多列・空セル過多)や文字化け表(Type3/ToUnicode欠落)は False とし、
    本文テキスト(get_text)のまま扱って退行を避ける。良品のみ Markdown 表に置換する。"""
    if t.row_count < 2 or t.col_count < 2 or t.col_count > 12:
        return False
    cells = [c for row in t.extract() for c in row]
    if not cells:
        return False
    empty = sum(1 for c in cells if not c or not str(c).strip())
    if empty / len(cells) > 0.35:          # 空セル過多 = 誤検出/複雑なセル結合表
        return False
    text = "".join(str(c) for c in cells if c)
    if not text:
        return False
    # 文字化け(NUL/置換文字/ラテン拡張の多用)を含む表はページ画像VLMに委ねる
    if _mojibake_ratio(text) > 0.05:
        return False
    return True


def extract_page_markdown(page, page_no, doc, page_images=False, no_vlm=False):
    parts = []

    # 罫線のある表を find_tables で構造保持(行列対応を残す)。良品のみ採用する。
    good_tables = []
    if not page_images:
        try:
            for t in page.find_tables().tables:
                if _is_good_table(t):
                    good_tables.append(t)
        except Exception:
            pass

    # 本文は全文を残す(表領域も除外しない)。find_tables の誤検出(箇条書き/段組みの
    # 表化)で本文が消えるのを防ぐため、構造化した表は本文に「追記」するだけにする。
    # Type3フォント等で ToUnicode が無いと get_text が全グリフを NUL(\x00)で返すため除去。
    body = page.get_text().strip().replace("\x00", "").strip()
    # ToUnicode CMap 破損フォントは get_text がラテン拡張へ誤マップし本文全体が文字化けする
    # (NUL除去では落ちない)。長文でも has_real_body=True となりVLMフォールバックを素通り
    # するため、比率で検知して本文・表を捨て、ページ全体をVLM OCRに委ねる。
    # しきい値3%: 正常ページは~0%、化けページは数%以上に出るため、他63本は誤発火0で分離する。
    # 表は数値が多くラベルだけ化けても比率が薄まるため、表品質判定の5%(_is_good_table)より
    # 低めに設定する。
    body_mojibake = bool(body) and _mojibake_ratio(body) > 0.03
    # no_vlm: VLM を一切使わない比較ベースライン。文字化けも OCR せず生の get_text を残す。
    if body_mojibake and not no_vlm:
        sys.stderr.write(
            f"  page{page_no} 本文文字化け検知 ({_mojibake_ratio(body)*100:.0f}%) "
            f"-> 本文/表を破棄しページ画像VLMへ\n"
        )
        body = ""
        good_tables = []
    if body:
        parts.append(body)

    # 採用した表を Markdown(行列保持)で本文に追記する(本文と二重化しても検索上は無害)。
    for ti, t in enumerate(good_tables, 1):
        parts.append(f"\n[Table {page_no}-{ti}]\n{t.to_markdown()}\n")

    # no_vlm: 図表VLM・ページOCR・フォールバックを全てスキップ(本文+find_tables のみ)。
    if no_vlm:
        return "\n\n".join(parts)

    # フォールバック判定用: 本文が薄くても表が取れていれば「本文あり」とみなす
    has_real_body = len(body) >= 40 or bool(good_tables)

    if page_images or body_mojibake:
        # ページ全体を画像化して VLM に渡す(ベクター図/スキャンPDF/本文文字化け向け)
        pix = page.get_pixmap(dpi=150)
        sys.stderr.write(f"  page{page_no} (full render {pix.width}x{pix.height}) -> VLM...\n")
        desc = vlm_describe_image(pix.tobytes("png"), "image/png")
        if not is_empty_vlm(desc):
            parts.append(f"\n[Page {page_no} rendering (extracted by vision model)]\n{desc}\n")
        return "\n\n".join(parts)

    useful_figs = 0
    for img in page.get_images(full=True):
        # RGB-PNG に正規化して送る(colorspace 拒否対策)
        png, w, h = img_xref_to_png(doc, img[0])
        if png is None or w < MIN_IMG_W or h < MIN_IMG_H:
            continue  # 取得失敗・アイコン等はスキップ
        sys.stderr.write(f"  page{page_no} fig ({w}x{h}) -> VLM...\n")
        desc = vlm_describe_image(png, "image/png")
        if is_empty_vlm(desc):
            continue  # エラー/装飾画像の無情報説明は捨てる
        useful_figs += 1
        parts.append(f"\n[Figure {page_no}-{useful_figs} (extracted by vision model)]\n{desc}\n")

    # 自動フォールバック: 本文が薄く有用な図表も拾えないページ(スキャン/ベクター/
    # Type3フォント/作図主体)は、ページ全体を画像化して VLM に OCR させる
    if not has_real_body and useful_figs == 0:
        pix = page.get_pixmap(dpi=150)
        sys.stderr.write(f"  page{page_no} (fallback full render {pix.width}x{pix.height}) -> VLM...\n")
        desc = vlm_describe_image(pix.tobytes("png"), "image/png")
        if not is_empty_vlm(desc):
            parts.append(f"\n[Page {page_no} rendering (extracted by vision model)]\n{desc}\n")

    return "\n\n".join(parts)


def pdf_to_markdown(pdf_path: Path, page_images=False, no_vlm=False) -> str:
    doc = fitz.open(pdf_path)
    md_pages = []
    for i, page in enumerate(doc):
        md_pages.append(f"## Page {i+1}\n\n" + extract_page_markdown(
            page, i + 1, doc, page_images, no_vlm))
    doc.close()
    title = pdf_path.stem
    return f"# {title}\n\n" + "\n\n---\n\n".join(md_pages)


def get_markdown(pdf_path: Path, page_images=False, use_cache=True, no_vlm=False) -> str:
    """VLM 抽出 Markdown を取得。キャッシュがあれば再利用する。
    no_vlm=.novlm.md / page_images=.pageimg.md。"""
    if no_vlm:
        suffix = ".novlm.md"
    elif page_images:
        suffix = ".pageimg.md"
    else:
        suffix = ".md"
    cache = CACHE_DIR / (pdf_path.stem + suffix)
    if use_cache and cache.is_file():
        sys.stderr.write(f"    cache 再利用: {cache}\n")
        return cache.read_text(encoding="utf-8")
    md = pdf_to_markdown(pdf_path, page_images, no_vlm)
    md, st = clean_markdown(md)  # 生成時もノイズ除去してから保存
    sys.stderr.write(f"    clean: 装飾削除{st['decor_dropped']} "
                     f"重複-{st['dedup_chars']}字 再分割{st['reseg']}段落\n")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(md, encoding="utf-8")
    sys.stderr.write(f"    Markdown保存(cache): {cache} ({len(md)}文字)\n")
    return md


# ---- メイン --------------------------------------------------
def select_pdfs(names) -> list:
    if names:
        out = []
        for n in names:
            p = Path(n)
            if not p.is_file():
                p = DOCS_DIR / n  # documents/ 配下のファイル名指定も許可
            if not p.is_file():
                die(f"PDF が見つかりません: {n}")
            out.append(p)
        return out
    return sorted(DOCS_DIR.glob("*.pdf"))


def main():
    ap = argparse.ArgumentParser(description="PDF を VLM で図表テキスト化して Dify に投入する")
    ap.add_argument("pdfs", nargs="*", help="対象PDF(省略時は documents/ 全件)。ファイル名のみ可")
    ap.add_argument("--sample", action="store_true", help="テスト用 pymupdf/documents/ 配下の PDF を対象にする")
    ap.add_argument("--limit", type=int, help="先頭 N 件だけ処理(例: --limit 1)")
    ap.add_argument("--dry-run", action="store_true", help="Dify に投入せず Markdown 生成のみ")
    ap.add_argument("--page-images", action="store_true", help="埋め込み画像でなくページ全体を画像化して VLM へ")
    ap.add_argument("--no-vlm", action="store_true",
                    help="VLMを一切使わず本文(get_text)+find_tablesのみで投入(VLM効果測定の対照。別キャッシュ .novlm.md / 別ナレッジは DIFY_DATASET_NAME で指定)")
    ap.add_argument("--refresh", action="store_true", help="キャッシュを無視して VLM を再実行")
    ap.add_argument("--clean-cache", action="store_true",
                    help="既存 vlm_cache/*.md を後処理(装飾削除/重複除去/再分割)して書き戻す。VLM 不要")
    ap.add_argument("--embedding-usage", action="store_true",
                    help="Dify ナレッジの embedding トークン(取込時)を集計表示。VLM/投入はしない")
    ap.add_argument("--force", action="store_true", help="同名ドキュメントが既存でも再投入する")
    ap.add_argument("--purge", action="store_true", help="投入前にナレッジ内の全ドキュメントを削除(作り直し用)")
    args = ap.parse_args()

    if args.clean_cache:
        clean_cache_files()
        return

    if args.embedding_usage:
        embedding_usage()
        return

    if not DOCS_DIR.is_dir():
        die(f"documents フォルダが見つかりません: {DOCS_DIR}")

    if args.sample:
        if not SAMPLE_PDF.is_file():
            die(f"documents/ 配下の PDF が見つかりません: {SAMPLE_PDF}")
        pdfs = [SAMPLE_PDF]
    else:
        pdfs = select_pdfs(args.pdfs)
    if args.limit:
        pdfs = pdfs[: args.limit]
    if not pdfs:
        die("対象PDFがありません")

    # dry-run 以外は Dify 準備
    ds_id, done = None, set()
    if not args.dry_run:
        if not API_KEY:
            die("環境変数 DIFY_KNOWLEDGE_API_KEY を設定してください(確認だけなら --dry-run)")
        ds_id = get_or_create_dataset()
        if args.purge:
            delete_all_documents(ds_id)
        done = existing_documents(ds_id)

    mode = 'no-vlm(text-only)' if args.no_vlm else ('page-images' if args.page_images else 'embedded-images')
    print(f"対象 {len(pdfs)} 件 / mode={mode} / {'DRY-RUN' if args.dry_run else 'UPLOAD'}"
          f" / ナレッジ={DATASET_NAME}")

    for i, pdf in enumerate(pdfs, 1):
        if not args.dry_run and not args.force and pdf.name in done:
            print(f"[{i}/{len(pdfs)}] skip(取込済): {pdf.name}")
            continue

        sys.stderr.write(f"[{i}/{len(pdfs)}] ==> 処理中: {pdf.name}\n")
        md = get_markdown(pdf, page_images=args.page_images, use_cache=not args.refresh,
                          no_vlm=args.no_vlm)

        if args.dry_run:
            print("=" * 70)
            print(md)
            print("=" * 70)
            continue

        try:
            res = push_to_dify(ds_id, pdf.name, md)
            doc = res.get("document", {})
            sys.stderr.write(f"    Dify投入OK: doc_id={doc.get('id','?')} "
                             f"status={doc.get('indexing_status','?')} batch={res.get('batch','?')}\n")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")[:300]
            sys.stderr.write(f"    Dify投入ERROR {e.code}: {body}\n")
            if e.code == 400 and "user account" in body.lower():
                sys.stderr.write("    → 書き込み権限のある user-scoped トークンが必要かもしれません\n")
        except Exception as e:
            sys.stderr.write(f"    Dify投入ERROR: {e}\n")
        time.sleep(1)  # インデキシング負荷を緩和

    if _VLM_TOK["calls"]:
        print(f"VLM 実呼び出し {_VLM_TOK['calls']}回 / "
              f"prompt={_VLM_TOK['prompt']:,} completion={_VLM_TOK['completion']:,} tok "
              f"→ 記録: {USAGE_LOG}")

    if not args.dry_run:
        print(f"\n完了。Dify UI でインデキシング完了を確認してください。 dataset_id: {ds_id}")


if __name__ == "__main__":
    main()
