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

`rag_evaluation_master.csv` と採用PDF manifest/checksum は Hugging Face dataset [SakataConsul/rag-eval-ja-repro](https://huggingface.co/datasets/SakataConsul/rag-eval-ja-repro) の公開物です。実行時は Hugging Face 側から `rag_evaluation_master.csv` を取得し、このリポジトリのルートに配置してください。

## 現行run

| run | 生成モデル | VLM図表化 | score |
|---|---|---:|---:|
| r1 | `openai/gpt-oss-20b` | no | 0.783 (235/300) |
| r2 | `openai/gpt-oss-20b` | yes | 0.823 (247/300) |
| r3 | `qwen/qwen3.6-35b-a3b` | no | 0.800 (240/300) |
| r4 | `qwen/qwen3.6-35b-a3b` | yes | 0.853 (256/300) |

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

`.env` にDify APIキーを設定します。

```bash
DIFY_KNOWLEDGE_API_KEY=dataset-xxxx
DIFY_APP_API_KEY=app-xxxx
```

既定の接続先とモデル:

- Dify API: `http://localhost`
- LM Studio OpenAI互換API: `http://localhost:1234`
- VLM: `qwen/qwen3-vl-8b`
- embedding: `Qwen/Qwen3-Embedding-8B-GGUF`
- Judge: `qwen/qwen3.6-35b-a3b`

## 入力を準備する

まず、Hugging Face dataset [SakataConsul/rag-eval-ja-repro](https://huggingface.co/datasets/SakataConsul/rag-eval-ja-repro) から `rag_evaluation_master.csv` を取得し、このGitHub repoのルートへ置きます。

```bash
# 例: Hugging Faceから取得したCSVを配置
cp /path/to/rag_evaluation_master.csv ./rag_evaluation_master.csv
```

次に、採用PDFを取得して SHA-256 を検証します。

```bash
python3 repro/download_documents.py
cd documents
shasum -a 256 -c ../repro/documents_checksums.sha256
cd ..
```

## r1-r4を実行する

まず、VLMあり/なしの2つのDifyナレッジを作成します。

```bash
set -a; source .env; set +a
./scripts/run_r1_r4_ingest.sh all
```

その後、Difyチャットボットのコンテキストを対象ナレッジへ切り替えてから、各runを実行します。

```bash
./scripts/run_r1_r4_chatbot.sh r1 generate --fresh
# Judge時は qwen/qwen3.6-35b-a3b をロード
./scripts/run_r1_r4_chatbot.sh r1 after-judge

./scripts/run_r1_r4_chatbot.sh r2 generate --fresh
# Judge時は qwen/qwen3.6-35b-a3b をロード
./scripts/run_r1_r4_chatbot.sh r2 after-judge

./scripts/run_r1_r4_chatbot.sh r3 all --fresh
./scripts/run_r1_r4_chatbot.sh r4 all --fresh
```

r1/r2は生成に `gpt-oss-20b`、Judgeに `qwen3.6-35b-a3b` を使うため、生成とJudgeを分けています。
