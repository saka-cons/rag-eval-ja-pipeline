# rag-eval-ja-pipeline

[RAG Eval JA Repro 再現用評価データセット](https://huggingface.co/datasets/SakataConsul/rag-eval-ja-repro)を [Dify + LM Studio で評価するためのパイプライン](https://qiita.com/sakata_ai/items/a45418f3611926826f66)です。

このリポジトリは、[Zenn Book「日本語RAGベンチマークをローカルで再現する」](https://zenn.dev/sakata_consul/books/rag-local-repro)で使った評価コードと実行成果物を置くためのものです。再現用評価データセット本体である `rag_evaluation_master.csv` は Hugging Face dataset [SakataConsul/rag-eval-ja-repro](https://huggingface.co/datasets/SakataConsul/rag-eval-ja-repro) 側を正とし、このGitHubリポジトリには同梱しません。

## 含めるもの

- Difyナレッジ取込スクリプト
- VLMによる図表テキスト化あり/なしの取込コード
- 回答生成、LLM-as-judge、集計、idx突合スクリプト
- r1-r4の公開成果物 `answers.csv` / `judged.csv` / `report.md` / `analysis.md`
- Difyアプリのテンプレート
- r1-r4で共通に使った生成システムプロンプト

## 含めないもの

- `rag_evaluation_master.csv`
- PDFバイナリ
- `vlm_cache/` / `vlm_imgcache/`
- `.env`
- Dify dataset id / APIキー

`rag_evaluation_master.csv` と採用PDF manifest/checksum は Hugging Face dataset [SakataConsul/rag-eval-ja-repro](https://huggingface.co/datasets/SakataConsul/rag-eval-ja-repro) の公開物です。この公開成果物では dataset commit [`0a9188a80844adbebe7c77746ba3c5949c6f549a`](https://huggingface.co/datasets/SakataConsul/rag-eval-ja-repro/commit/0a9188a80844adbebe7c77746ba3c5949c6f549a) を使用しました。

- `rag_evaluation_master.csv` SHA-256: `e7d93c1c616db837072576cae739fcbd157d65e1006aa5e7a63ada3e09acef8f`

## 現行run

| run | 生成モデル | VLM図表化 | score |
|---|---|---:|---:|
| r1 | `openai/gpt-oss-20b` | no | 0.760 (228/300) |
| r2 | `openai/gpt-oss-20b` | yes | 0.823 (247/300) |
| r3 | `qwen/qwen3.6-35b-a3b` | no | 0.797 (239/300) |
| r4 | `qwen/qwen3.6-35b-a3b` | yes | 0.870 (261/300) |

これらの値は、HF dataset 側の `rag_evaluation_master.csv` 再現用評価基準CSVと Qwen Judge を使った結果です。参照元データセットのリーダーボードと同一の順位表として扱うものではありません。PDFのバイト一致検証も、この再現用評価データセットで採用したPDF集合に対する検証であり、リーダーボード作成時の内部コーパスとの同一性を証明するものではありません。

## 構成

| path | 役割 |
|---|---|
| `repro/` | 採用PDFの取得・検証スクリプト。CSV本体はHF dataset側を参照。 |
| `prompts/generation_system_prompt.md` | r1-r4で共通に使ったDify生成システムプロンプト。 |
| `scripts/` | 取込、回答生成、Judge、集計、比較、成果物整理スクリプト。 |
| `dify/dify_app_template.yml` | Difyアプリテンプレート。import後にdataset idを差し替える。 |
| `results/r1`...`results/r4` | 公開run成果物。 |
| `analysis/` | 記事で使った横断分析。 |

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` にDify APIキーと接続先を設定します。

```bash
DIFY_BASE_URL=http://localhost
DIFY_KNOWLEDGE_API_KEY=dataset-xxxx
DIFY_ADMIN_API_KEY=console-access-token-xxxx
```

Difyナレッジ操作には `DIFY_KNOWLEDGE_API_KEY` を使います。r1-r4用のチャットアプリ作成、dataset id紐づけ、アプリAPIキー発行には Dify Console API を使います。

ローカルself-hosted Difyを `../dify_rag/dify/docker/docker-compose.yaml` で動かしている場合、runnerは `scripts/dify_console_token_from_docker.sh` で短期の `DIFY_CONSOLE_ACCESS_TOKEN` / `DIFY_CONSOLE_CSRF_TOKEN` を自動生成します。composeファイルの場所が異なる場合は `DIFY_DOCKER_COMPOSE` を指定してください。外部Difyを使う場合は `.env` に `DIFY_CONSOLE_ACCESS_TOKEN` と、CSRF検証が有効な環境では `DIFY_CONSOLE_CSRF_TOKEN` を設定します。`DIFY_ADMIN_API_KEY` は互換用で、`DIFY_CONSOLE_ACCESS_TOKEN` があればそちらを優先します。既存の単体アプリを直接使う場合だけ `DIFY_APP_API_KEY` を設定します。

既定の接続先とモデル:

- Dify API: `http://localhost`
- LM Studio OpenAI互換API: `http://localhost:1234`
- VLM: `qwen/qwen3-vl-8b`
- embedding: `Qwen/Qwen3-Embedding-8B-GGUF`
- Judge: `qwen/qwen3.6-35b-a3b`

## 入力を準備する

まず、上記のdataset commitから `rag_evaluation_master.csv` を取得し、このGitHub repoのルートへ置きます。

```bash
curl -L \
  -o rag_evaluation_master.csv \
  https://huggingface.co/datasets/SakataConsul/rag-eval-ja-repro/resolve/0a9188a80844adbebe7c77746ba3c5949c6f549a/rag_evaluation_master.csv
echo "e7d93c1c616db837072576cae739fcbd157d65e1006aa5e7a63ada3e09acef8f  rag_evaluation_master.csv" | shasum -a 256 -c -
```

次に、採用PDFを取得して SHA-256 を検証します。

```bash
python3 repro/download_documents.py
cd documents
shasum -a 256 -c ../repro/documents_checksums.sha256
cd ..
```

## r1-r4を実行する

通常は一気通貫runnerを使います。Difyナレッジ作成、Difyチャットアプリ作成、dataset id紐づけ、回答生成、Judge、集計、断面保存まで行います。

```bash
set -a; source .env; set +a
./scripts/run_r1_r4_full.sh
```

スクリプトはLM Studioのモデル切替が必要な箇所で停止します。

1. VLM/embedding利用前: `qwen/qwen3-vl-8b` と `Qwen/Qwen3-Embedding-8B-GGUF` を利用可能にする
2. r1/r2生成前: `openai/gpt-oss-20b` をロードし、`qwen/qwen3.6-35b-a3b` をunload
3. r1/r2 Judgeとr3/r4実行前: `openai/gpt-oss-20b` をunloadし、`qwen/qwen3.6-35b-a3b` をロード

runごとの中間生成物は `results/_snapshots/<run_id>/` に保存されます。`results/r1`...`results/r4` には old状態と同じ公開成果物面を再生成します。

r1/r2は生成に `gpt-oss-20b`、Judgeに `qwen3.6-35b-a3b` を使うため、生成とJudgeを分けています。
