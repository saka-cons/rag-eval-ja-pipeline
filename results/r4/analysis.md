# r4 analysis

- generated_at: 2026-07-12T06:37:28
- label: r4: VLM + qwen3.6-35b-a3b
- knowledge_mode: vlm
- dify_dataset_name: `RAG-JA-20260711-1010-e7d93c1c-vlm`
- generation_model: `qwen/qwen3.6-35b-a3b`
- judge_model: `qwen/qwen3.6-35b-a3b`
- score: **0.870 (261/300)**
- answers_rows: 300
- judged_rows: 300
- ox_counts: {'O': 261, 'X': 39}
- answer_errors: 0
- generation_tokens: prompt=2,807,045 / completion=1,636,462
- judge_tokens: prompt=180,826 / completion=480,916
- vlm_cache_files: 65
- vlm_imgcache_files: 1032

## Domain Scores

| domain | score |
|---|---|
| finance | 0.850 (51/60) |
| it | 0.867 (52/60) |
| manufacturing | 0.867 (52/60) |
| public | 0.883 (53/60) |
| retail | 0.883 (53/60) |

## Type Scores

| type | score |
|---|---|
| paragraph | 0.923 (131/142) |
| table | 0.866 (71/82) |
| image | 0.776 (59/76) |

## Reproduction Notes

- `answers.csv` and `judged.csv` are the primary run outputs.
- The local run used a copied `rag_evaluation_master.csv`; the public artifact omits it and pins the source dataset commit in the repository README.
- The local run generated `vlm_cache/` and `vlm_imgcache/`; the public artifact omits both cache directories.
