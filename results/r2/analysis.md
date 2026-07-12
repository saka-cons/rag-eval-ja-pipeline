# r2 analysis

- generated_at: 2026-07-11T18:48:10
- label: r2: VLM + gpt-oss-20b
- knowledge_mode: vlm
- dify_dataset_name: `RAG-JA-20260711-1010-e7d93c1c-vlm`
- generation_model: `openai/gpt-oss-20b`
- judge_model: `qwen/qwen3.6-35b-a3b`
- score: **0.823 (247/300)**
- answers_rows: 300
- judged_rows: 300
- ox_counts: {'X': 53, 'O': 247}
- answer_errors: 0
- generation_tokens: prompt=2,807,045 / completion=326,664
- judge_tokens: prompt=212,202 / completion=500,932
- vlm_cache_files: 65
- vlm_imgcache_files: 1032

## Domain Scores

| domain | score |
|---|---|
| finance | 0.750 (45/60) |
| it | 0.867 (52/60) |
| manufacturing | 0.833 (50/60) |
| public | 0.833 (50/60) |
| retail | 0.833 (50/60) |

## Type Scores

| type | score |
|---|---|
| paragraph | 0.859 (122/142) |
| table | 0.829 (68/82) |
| image | 0.750 (57/76) |

## Reproduction Notes

- `answers.csv` and `judged.csv` are the primary run outputs.
- The local run used a copied `rag_evaluation_master.csv`; the public artifact omits it and pins the source dataset commit in the repository README.
- The local run generated `vlm_cache/` and `vlm_imgcache/`; the public artifact omits both cache directories.
