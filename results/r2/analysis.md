# r2 analysis

- generated_at: 2026-06-28T09:03:18
- label: r2: VLM + gpt-oss-20b
- knowledge_mode: vlm
- dify_dataset_name: `RAG-Eval-JA-master-vlm`
- generation_model: `openai/gpt-oss-20b`
- judge_model: `qwen/qwen3.6-35b-a3b`
- score: **0.823 (247/300)**
- answers_rows: 300
- judged_rows: 300
- ox_counts: {'O': 247, 'X': 53}
- answer_errors: 0
- generation_tokens: prompt=2,805,137 / completion=328,383
- judge_tokens: prompt=212,694 / completion=485,130
- vlm_cache_files: 65
- vlm_imgcache_files: 1016

## Domain Scores

| domain | score |
|---|---|
| finance | 0.750 (45/60) |
| it | 0.850 (51/60) |
| manufacturing | 0.833 (50/60) |
| public | 0.850 (51/60) |
| retail | 0.833 (50/60) |

## Type Scores

| type | score |
|---|---|
| paragraph | 0.866 (123/142) |
| table | 0.841 (69/82) |
| image | 0.724 (55/76) |

## Reproduction Notes

- `answers.csv` and `judged.csv` are the primary run outputs.
- The evaluation target is the Hugging Face dataset release `rag_evaluation_master.csv`, placed at the GitHub repo root when rerunning.
- `vlm_cache/` is not distributed in this public package; `vlm_cache_files` records the source run cache count.
- `vlm_imgcache/` is not distributed in this public package; `vlm_imgcache_files` records the source run cache count.
