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

`rag_evaluation_master.csv` は Hugging Face dataset 側を正とします。このGitHub repoには同梱しません。この公開成果物は dataset commit [`0a9188a80844adbebe7c77746ba3c5949c6f549a`](https://huggingface.co/datasets/SakataConsul/rag-eval-ja-repro/commit/0a9188a80844adbebe7c77746ba3c5949c6f549a) を使用しています。

```bash
curl -L \
  -o rag_evaluation_master.csv \
  https://huggingface.co/datasets/SakataConsul/rag-eval-ja-repro/resolve/0a9188a80844adbebe7c77746ba3c5949c6f549a/rag_evaluation_master.csv
echo "e7d93c1c616db837072576cae739fcbd157d65e1006aa5e7a63ada3e09acef8f  rag_evaluation_master.csv" | shasum -a 256 -c -
```

## 3. 採用PDFを取得

```bash
python3 repro/download_documents.py
cd documents
shasum -a 256 -c ../repro/documents_checksums.sha256
cd ..
```

## 4. Dify と LM Studio を設定

`.env` に次の値を設定します。

```bash
DIFY_BASE_URL=http://localhost
DIFY_KNOWLEDGE_API_KEY=dataset-xxxx
DIFY_ADMIN_API_KEY=console-access-token-xxxx
```

`DIFY_KNOWLEDGE_API_KEY` はナレッジ作成、indexing待機、retrieve検証に使います。`dify/dify_app_template.yml` のimport、dataset idの差し替え、アプリAPIキー発行には Dify Console API を使います。

ローカルself-hosted Difyを `../dify_rag/dify/docker/docker-compose.yaml` で動かしている場合、`./scripts/run_r1_r4_full.sh` は `scripts/dify_console_token_from_docker.sh` で短期の `DIFY_CONSOLE_ACCESS_TOKEN` / `DIFY_CONSOLE_CSRF_TOKEN` を自動生成します。composeファイルの場所が異なる場合は `DIFY_DOCKER_COMPOSE` を設定してください。外部Difyを使う場合は `.env` に `DIFY_CONSOLE_ACCESS_TOKEN` と、CSRF検証が有効な環境では `DIFY_CONSOLE_CSRF_TOKEN` を設定します。`DIFY_ADMIN_API_KEY` は互換用で、`DIFY_CONSOLE_ACCESS_TOKEN` があればそちらを優先します。

LM Studioでは、必要に応じて次のモデルをロードします。

| 用途 | モデル |
|---|---|
| VLM extraction | `qwen/qwen3-vl-8b` |
| embedding | `Qwen/Qwen3-Embedding-8B-GGUF` |
| generation / judge | `qwen/qwen3.6-35b-a3b` |
| generation alternative | `openai/gpt-oss-20b` |

## 5. 一気通貫実行

通常は次のrunnerを使います。

```bash
set -a; source .env; set +a
./scripts/run_r1_r4_full.sh
```

runnerは次を順に行います。

1. `documents/` のPDF取得とSHA-256検証
2. VLMあり/なしのDifyナレッジ作成
3. Dify indexing metadata と retrieve API の検証
4. r1-r4用Difyチャットアプリの作成/更新とdataset id紐づけ
5. r1-r4の回答生成、Judge、集計、成果物整理
6. `analysis/` の再生成
7. old状態と同じ成果物面の検証

次の箇所だけ、LM Studio操作のために一時停止します。

- VLM/embedding利用前: `qwen/qwen3-vl-8b` と `Qwen/Qwen3-Embedding-8B-GGUF` を利用可能にする
- r1/r2生成前: `openai/gpt-oss-20b` をロードし、`qwen/qwen3.6-35b-a3b` をunload
- r1/r2 Judgeとr3/r4実行前: `openai/gpt-oss-20b` をunloadし、`qwen/qwen3.6-35b-a3b` をロード

run断面は `results/_snapshots/<run_id>/` に保存します。公開成果物面は `results/r1`...`results/r4` と `analysis/` に出力します。

## 6. 分割実行

runnerを使わずに分割する場合、まずVLMあり/なしの2つのナレッジを作成します。

```bash
set -a; source .env; set +a
./scripts/run_r1_r4_ingest.sh all --no-purge
```

既定では次の2つのナレッジを作成します。

- `RAG-Eval-JA-master-vlm`
- `RAG-Eval-JA-master-novlm`

断面ごとに分けたい場合は、次の環境変数でdataset名を指定します。

```bash
export DIFY_DATASET_VLM_NAME=RAG-JA-manual-vlm
export DIFY_DATASET_NOVLM_NAME=RAG-JA-manual-novlm
./scripts/run_r1_r4_ingest.sh all --no-purge
```

Difyアプリは `scripts/dify_resources.py ensure-app` で作成し、run別app API keyを環境変数に書き出します。

```bash
mkdir -p results/_snapshots/manual/state
KEY_ENV=results/_snapshots/manual/state/dify_app_keys.env
: > "$KEY_ENV"
python3 scripts/dify_resources.py ensure-app \
  --run r1 --run-slug manual \
  --dataset-name "${DIFY_DATASET_NOVLM_NAME:-RAG-Eval-JA-master-novlm}" \
  --generation-model openai/gpt-oss-20b \
  --key-env "$KEY_ENV" --env-name DIFY_APP_API_KEY_R1
source "$KEY_ENV"
./scripts/run_r1_r4_chatbot.sh r1 generate --fresh
./scripts/run_r1_r4_chatbot.sh r1 after-judge
```

同じ要領で r2-r4 のappを作成してから実行します。

```bash
./scripts/run_r1_r4_chatbot.sh r2 generate --fresh
./scripts/run_r1_r4_chatbot.sh r2 after-judge
./scripts/run_r1_r4_chatbot.sh r3 all --fresh
./scripts/run_r1_r4_chatbot.sh r4 all --fresh
```

idx単位の対応比較:

```bash
python3 scripts/compare_versions.py --base r1/judged.csv --new r2/judged.csv
```

old状態と同じ成果物面を確認します。

```bash
python3 scripts/run_snapshot.py verify
```
