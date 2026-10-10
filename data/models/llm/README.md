# Local language model

| File | Model | Size | SHA-256 |
|---|---|---|---|
| `Llama-3.2-3B-Instruct-Q4_K_S.gguf` (Git LFS) | Meta Llama 3.2 3B Instruct, 4-bit GGUF quantisation (bartowski/Llama-3.2-3B-Instruct-GGUF) | 1,928,200,736 bytes | bfb5db97e77e3927e18d971806e36d1886271d6c62e160d5bc78bcdbefb7197c |

**Built with Llama.** Llama 3.2 is licensed under the Llama 3.2 Community License, Copyright © Meta Platforms, Inc.
All Rights Reserved. See `LICENSE` and `USE_POLICY.md` in this folder.

Used only as an assistant: plain-language estimate summaries (every number checked against the estimate). It never
calculates quantities, rates or totals. Measured on real price pages, 1B/3B models misread most figures, so web price
reading uses the rule-based parser unless a Llama 3.1 8B (Ollama) is configured.
