# r4 analysis

- generated_at: 2026-06-28T09:03:18
- label: r4: VLM + qwen3.6-35b-a3b
- knowledge_mode: vlm
- dify_dataset_name: `RAG-Eval-JA-master-vlm`
- generation_model: `qwen/qwen3.6-35b-a3b`
- judge_model: `qwen/qwen3.6-35b-a3b`
- score: **0.853 (256/300)**
- answers_rows: 300
- judged_rows: 300
- ox_counts: {'X': 44, 'O': 256}
- answer_errors: 0
- generation_tokens: prompt=2,805,137 / completion=1,668,626
- judge_tokens: prompt=177,476 / completion=485,936
- vlm_cache_files: 65
- vlm_imgcache_files: 1016

## Domain Scores

| domain | score |
|---|---|
| finance | 0.767 (46/60) |
| it | 0.933 (56/60) |
| manufacturing | 0.817 (49/60) |
| public | 0.867 (52/60) |
| retail | 0.883 (53/60) |

## Type Scores

| type | score |
|---|---|
| paragraph | 0.937 (133/142) |
| table | 0.817 (67/82) |
| image | 0.737 (56/76) |

## Reproduction Notes

- `answers.csv` and `judged.csv` are the primary run outputs.
- The evaluation target is the Hugging Face dataset release `rag_evaluation_master.csv`, placed at the GitHub repo root when rerunning.
- `vlm_cache/` is not distributed in this public package; `vlm_cache_files` records the source run cache count.
- `vlm_imgcache/` is not distributed in this public package; `vlm_imgcache_files` records the source run cache count.
