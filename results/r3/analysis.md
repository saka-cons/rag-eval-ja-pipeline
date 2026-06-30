# r3 analysis

- generated_at: 2026-06-28T09:03:18
- label: r3: no-VLM + qwen3.6-35b-a3b
- knowledge_mode: novlm
- dify_dataset_name: `RAG-Eval-JA-master-novlm`
- generation_model: `qwen/qwen3.6-35b-a3b`
- judge_model: `qwen/qwen3.6-35b-a3b`
- score: **0.800 (240/300)**
- answers_rows: 300
- judged_rows: 300
- ox_counts: {'O': 240, 'X': 60}
- answer_errors: 0
- generation_tokens: prompt=3,178,090 / completion=1,670,641
- judge_tokens: prompt=177,688 / completion=484,460
- vlm_cache_files: 65
- vlm_imgcache_files: 0

## Domain Scores

| domain | score |
|---|---|
| finance | 0.683 (41/60) |
| it | 0.850 (51/60) |
| manufacturing | 0.733 (44/60) |
| public | 0.900 (54/60) |
| retail | 0.833 (50/60) |

## Type Scores

| type | score |
|---|---|
| paragraph | 0.908 (129/142) |
| table | 0.878 (72/82) |
| image | 0.513 (39/76) |

## Reproduction Notes

- `answers.csv` and `judged.csv` are the primary run outputs.
- The evaluation target is the Hugging Face dataset release `rag_evaluation_master.csv`, placed at the GitHub repo root when rerunning.
- `vlm_cache/` is not distributed in this public package; `vlm_cache_files` records the source run cache count.
- `vlm_imgcache/` is not distributed in this public package; `vlm_imgcache_files` records the source run cache count.
