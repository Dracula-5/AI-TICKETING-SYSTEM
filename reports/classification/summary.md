# P4.1 Ticket classification — results

Dataset: public support-ticket texts (LLM-generated, CC BY-NC 4.0), English, exact duplicates removed, stratified 70/15/15 split. Models selected on validation macro-F1; **test split scored once**. Latency: single ticket, CPU, p50 over 200 test tickets (includes embedding for embedding models). Provenance: `reports/classification/p4_text_classification.json`.

Leakage check: median max TF-IDF cosine of a test ticket to the train set = 0.57; 11.6% of test tickets have a train near-duplicate (cosine ≥ 0.8). 'Novel macro-F1' is computed on the remaining test tickets.

## queue

| Model | Accuracy | Macro F1 (95% CI) | Weighted F1 | Novel macro-F1 | p50 latency |
|---|---|---|---|---|---|
| Majority class | 0.290 | 0.045 (0.043–0.047) | 0.130 |  |  |
| TF-IDF + LogReg | 0.631 | 0.637 (0.609–0.664) | 0.631 | 0.591 | 2.0 ms |
| TF-IDF + LinearSVC | 0.673 | 0.676 (0.651–0.701) | 0.673 | 0.629 | 3.0 ms |
| all-MiniLM-L6-v2 embeddings + LogReg | 0.318 | 0.303 (0.286–0.321) | 0.328 | 0.293 | 74.0 ms |
| bge-small-en-v1.5 embeddings + LogReg | 0.325 | 0.307 (0.290–0.324) | 0.334 | 0.303 | 126.2 ms |

## type

| Model | Accuracy | Macro F1 (95% CI) | Weighted F1 | Novel macro-F1 | p50 latency |
|---|---|---|---|---|---|
| Majority class | 0.404 | 0.144 (0.139–0.149) | 0.233 |  |  |
| TF-IDF + LogReg | 0.866 | 0.878 (0.867–0.889) | 0.867 | 0.867 | 2.1 ms |
| TF-IDF + LinearSVC | 0.882 | 0.892 (0.881–0.902) | 0.882 | 0.880 | 0.9 ms |
| all-MiniLM-L6-v2 embeddings + LogReg | 0.769 | 0.796 (0.781–0.809) | 0.774 | 0.790 | 31.3 ms |
| bge-small-en-v1.5 embeddings + LogReg | 0.775 | 0.802 (0.788–0.816) | 0.780 | 0.796 | 56.3 ms |

## priority

| Model | Accuracy | Macro F1 (95% CI) | Weighted F1 | Novel macro-F1 | p50 latency |
|---|---|---|---|---|---|
| Majority class | 0.396 | 0.189 (0.182–0.196) | 0.224 |  |  |
| TF-IDF + LogReg | 0.681 | 0.668 (0.647–0.686) | 0.681 | 0.627 | 0.8 ms |
| TF-IDF + LinearSVC | 0.703 | 0.689 (0.668–0.707) | 0.702 | 0.648 | 0.7 ms |
| all-MiniLM-L6-v2 embeddings + LogReg | 0.443 | 0.434 (0.413–0.454) | 0.446 | 0.423 | 31.6 ms |
| bge-small-en-v1.5 embeddings + LogReg | 0.475 | 0.467 (0.447–0.485) | 0.477 | 0.465 | 52.5 ms |
