# r1 analysis

- generated_at: 2026-07-11T16:52:39
- label: r1: no-VLM + gpt-oss-20b
- knowledge_mode: novlm
- dify_dataset_name: `RAG-JA-20260711-1010-e7d93c1c-novlm`
- generation_model: `openai/gpt-oss-20b`
- judge_model: `qwen/qwen3.6-35b-a3b`
- score: **0.760 (228/300)**
- answers_rows: 300
- judged_rows: 300
- ox_counts: {'X': 72, 'O': 228}
- answer_errors: 0
- generation_tokens: prompt=3,186,107 / completion=330,162
- judge_tokens: prompt=212,949 / completion=497,724
- vlm_cache_files: 65
- vlm_imgcache_files: 0

## Domain Scores

| domain | score |
|---|---|
| finance | 0.667 (40/60) |
| it | 0.783 (47/60) |
| manufacturing | 0.750 (45/60) |
| public | 0.817 (49/60) |
| retail | 0.783 (47/60) |

## Type Scores

| type | score |
|---|---|
| paragraph | 0.880 (125/142) |
| table | 0.817 (67/82) |
| image | 0.474 (36/76) |

## Reproduction Notes

- `answers.csv` and `judged.csv` are the primary run outputs.
- The local run used a copied `rag_evaluation_master.csv`; the public artifact omits it and pins the source dataset commit in the repository README.
- The local run generated `vlm_cache/` and `vlm_imgcache/`; the public artifact omits both cache directories.
