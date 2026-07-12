# r3 analysis

- generated_at: 2026-07-12T00:54:25
- label: r3: no-VLM + qwen3.6-35b-a3b
- knowledge_mode: novlm
- dify_dataset_name: `RAG-JA-20260711-1010-e7d93c1c-novlm`
- generation_model: `qwen/qwen3.6-35b-a3b`
- judge_model: `qwen/qwen3.6-35b-a3b`
- score: **0.797 (239/300)**
- answers_rows: 300
- judged_rows: 300
- ox_counts: {'O': 239, 'X': 61}
- answer_errors: 0
- generation_tokens: prompt=3,186,107 / completion=1,749,164
- judge_tokens: prompt=176,839 / completion=476,048
- vlm_cache_files: 65
- vlm_imgcache_files: 0

## Domain Scores

| domain | score |
|---|---|
| finance | 0.667 (40/60) |
| it | 0.883 (53/60) |
| manufacturing | 0.733 (44/60) |
| public | 0.833 (50/60) |
| retail | 0.867 (52/60) |

## Type Scores

| type | score |
|---|---|
| paragraph | 0.915 (130/142) |
| table | 0.866 (71/82) |
| image | 0.500 (38/76) |

## Reproduction Notes

- `answers.csv` and `judged.csv` are the primary run outputs.
- The local run used a copied `rag_evaluation_master.csv`; the public artifact omits it and pins the source dataset commit in the repository README.
- The local run generated `vlm_cache/` and `vlm_imgcache/`; the public artifact omits both cache directories.
