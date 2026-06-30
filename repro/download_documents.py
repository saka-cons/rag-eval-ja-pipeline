#!/usr/bin/env python3
"""
再現用評価データセットで採用するPDF 65本を、固定URLから取得するスクリプト。

Wayback Machine の特定スナップショット(タイムスタンプ固定URL=archive_pinned)から
取得し、取得したPDFが本データセットの manifest に記録した SHA-256 と一致するかを検証する。
これは「リーダーボード作成時の内部コーパスと同一である」ことの証明ではなく、
本データセットで採用したPDF集合を第三者が同じバイト列で取得するための手順である。
(元アーカイブが無かった数本は Save Page Now で固定スナップショットを作成済み。例:
 r04_04_03.pdf は発行元が差し替え済みだったため 2026/06/20 に固定し、採用版とバイト一致を確認。)

使い方(リポジトリルートから):
    # 既定で repro/download_sources.csv を読み documents/ へ出力する
    python3 repro/download_documents.py
    # 明示する場合:
    python3 repro/download_documents.py -s repro/download_sources.csv -o documents
    # 取得後の検証:
    cd documents && shasum -a 256 -c ../repro/documents_checksums.sha256

挙動:
    - pinned_archive_url があればそれを最優先で取得（=固定スナップショット）。
      現状 download_sources.csv は全65行が archive_pinned。
    - 万一 pinned_archive_url が空の行があれば source_url から直接取得にフォールバックする
      (取得時期により版が異なりうるが、その場合は checksum 不一致で検出できる)。
"""
import argparse, csv, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

def is_pdf(path):
    try:
        with open(path, "rb") as f:
            return f.read(5).startswith(b"%PDF")
    except OSError:
        return False

def fetch(url, dest, timeout=90, retries=4):
    # Wayback は単一IPで負荷分散しており、連続アクセスで一時的に接続拒否(=レート制限)に
    # なることがある。指数バックオフで数回リトライすれば概ね取り切れる。
    tmp = dest + ".part"
    for attempt in range(retries):
        # --compressed: Wayback の一部スナップショットは gzip エンコードで配信されるため、
        # curl 側で展開させて生PDFを得る。
        subprocess.run(["curl", "-sL", "--compressed", "--max-time", str(timeout),
                        "-A", UA, "-o", tmp, url], capture_output=True)
        if os.path.exists(tmp) and is_pdf(tmp):
            os.replace(tmp, dest)
            return True
        if os.path.exists(tmp):
            os.remove(tmp)
        if attempt < retries - 1:
            time.sleep(5 * (attempt + 1))   # 5s, 10s, 15s …
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-s", "--sources", default=os.path.join(HERE, "download_sources.csv"))
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "documents"))
    ap.add_argument("--delay", type=float, default=1.5,
                    help="ネットワーク取得ごとの待機秒(Waybackのレート制限回避)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    rows = list(csv.DictReader(open(args.sources, encoding="utf-8-sig")))
    pinned = direct = fail = 0

    for r in rows:
        fn = r["file_name"]
        dest = os.path.join(args.out, fn)
        if is_pdf(dest):
            print(f"[skip] {fn}")
            continue
        time.sleep(args.delay)   # 取得が必要な行のみ待機(skip は待たない)
        purl = r.get("pinned_archive_url", "").strip()
        if purl:
            if fetch(purl, dest):
                print(f"[pin]  {fn}")
                pinned += 1
            else:
                print(f"[FAIL] {fn}  {purl}", file=sys.stderr)
                fail += 1
            continue
        # pinned_archive_url が空の行のフォールバック(現状 sources は全行 pinned のため通常は通らない)。source_url から直接取得。
        if fetch(r["source_url"], dest):
            print(f"[dir]  {fn}  (source_url直接取得・版が異なる可能性あり)")
            direct += 1
        else:
            print(f"[FAIL] {fn}  {r['source_url']}", file=sys.stderr)
            fail += 1

    print(f"\ndone: pinned={pinned}  direct={direct}  fail={fail}  total={len(rows)}")
    print("検証:  cd %s && shasum -a 256 -c %s" % (args.out, os.path.join(HERE, "documents_checksums.sha256")))
    sys.exit(1 if fail else 0)

if __name__ == "__main__":
    main()
