# r1 analysis

- generated_at: 2026-06-28T09:03:17
- label: r1: no-VLM + gpt-oss-20b
- knowledge_mode: novlm
- dify_dataset_name: `RAG-Eval-JA-master-novlm`
- generation_model: `openai/gpt-oss-20b`
- judge_model: `qwen/qwen3.6-35b-a3b`
- score: **0.783 (235/300)**
- answers_rows: 300
- judged_rows: 300
- ox_counts: {'O': 235, 'X': 65}
- answer_errors: 0
- generation_tokens: prompt=3,178,090 / completion=321,560
- judge_tokens: prompt=210,414 / completion=487,331
- vlm_cache_files: 65
- vlm_imgcache_files: 0

## Domain Scores

| domain | score |
|---|---|
| finance | 0.700 (42/60) |
| it | 0.833 (50/60) |
| manufacturing | 0.733 (44/60) |
| public | 0.850 (51/60) |
| retail | 0.800 (48/60) |

## Type Scores

| type | score |
|---|---|
| paragraph | 0.901 (128/142) |
| table | 0.841 (69/82) |
| image | 0.500 (38/76) |

## Reproduction Notes

- `answers.csv` and `judged.csv` are the primary run outputs.
- The evaluation target is the Hugging Face dataset release `rag_evaluation_master.csv`, placed at the GitHub repo root when rerunning.
- `vlm_cache/` is not distributed in this public package; `vlm_cache_files` records the source run cache count.
- `vlm_imgcache/` is not distributed in this public package; `vlm_imgcache_files` records the source run cache count.
