# Local language model — Google Gemma 3 4B

| File | Model | Size | SHA-256 |
|---|---|---|---|
| `google_gemma-3-4b-it-Q4_K_M.gguf` | Gemma 3 4B instruction-tuned, 4-bit GGUF (bartowski/google_gemma-3-4b-it-GGUF) | 2,489,758,112 bytes | 4996030242583a40aa151ff93f49ed787ac8c25e4120c3ae4588b2e2a7d1ae94 |

GitHub's Git LFS limit is 2 GB per file, so the repository stores the file as `…gguf.part1` and `…gguf.part2`
(Git LFS). The start scripts join them once and verify the SHA-256 above (`backend/model_file.py`).

**Gemma is provided under and subject to the Gemma Terms of Use found at ai.google.dev/gemma/terms.**
Copies: `GEMMA_TERMS_OF_USE.txt` and `GEMMA_PROHIBITED_USE_POLICY.txt` in this folder. This file is unmodified
(a format conversion/quantisation published by a third party); no fine-tuning was done.

Use in PWD Estimator — an assistant only, never the estimator:
- plain-language estimate summaries (every number in the reply must appear in the estimate, otherwise rejected)
- reading construction ₹/sq ft from web price pages (each figure must quote the page; land / rent / other-city
  prices are rejected; results are indicative market ranges, never PWD rates)

Measured on three real Tamil Nadu price pages (CPU): Llama 3.2 1B found nothing usable, Llama 3.2 3B missed most
figures, Gemma 3 4B read all three pages (some package tiers mislabelled), Llama 3.1 8B (GPU) read all tiers.
