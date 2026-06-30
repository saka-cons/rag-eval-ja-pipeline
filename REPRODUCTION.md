# 再実行手順

この手順は、RAG Eval JA Repro 再現用評価データセットに対する評価パイプラインを再実行するためのものです。参照元リーダーボード作成時の内部コーパスを再現・証明するものではありません。

## 1. 依存関係

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 2. 再現用評価基準CSVを配置

`rag_evaluation_master.csv` は Hugging Face dataset 側を正とします。このGitHub repoには同梱しません。

```bash
cp /path/to/rag_evaluation_master.csv ./rag_evaluation_master.csv
```

## 3. 採用PDFを取得

```bash
python3 repro/download_documents.py
cd documents
shasum -a 256 -c ../repro/documents_checksums.sha256
cd ..
```

## 4. Dify と LM Studio を設定

`dify/dify_app_template.yml` をDifyへimportし、対象ナレッジ作成後にdataset idを差し替えます。

LM Studioでは、必要に応じて次のモデルをロードします。

| 用途 | モデル |
|---|---|
| VLM extraction | `qwen/qwen3-vl-8b` |
| embedding | `Qwen/Qwen3-Embedding-8B-GGUF` |
| generation / judge | `qwen/qwen3.6-35b-a3b` |
| generation alternative | `openai/gpt-oss-20b` |

## 5. 取込

```bash
set -a; source .env; set +a
./scripts/run_r1_r4_ingest.sh all
```

次の2つのナレッジを作成します。

- `RAG-Eval-JA-master-vlm`
- `RAG-Eval-JA-master-novlm`

Difyアプリ側のコンテキストを、実行するrunに応じて手動で切り替えてください。

## 6. 回答生成、Judge、集計

```bash
./scripts/run_r1_r4_chatbot.sh r1 generate --fresh
./scripts/run_r1_r4_chatbot.sh r1 after-judge
./scripts/run_r1_r4_chatbot.sh r2 generate --fresh
./scripts/run_r1_r4_chatbot.sh r2 after-judge
./scripts/run_r1_r4_chatbot.sh r3 all --fresh
./scripts/run_r1_r4_chatbot.sh r4 all --fresh
```

idx単位の対応比較:

```bash
python3 scripts/compare_versions.py --base r1/judged.csv --new r2/judged.csv
```
