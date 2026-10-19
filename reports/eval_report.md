# GraphTrace evaluation report

_Generated from `reports/eval_results.json`. Every number below was measured in this run._

## Run configuration

| Item | Value |
|---|---|
| Run started (UTC) | 2026-10-19T05:13:14+00:00 |
| Answer model | gemini-3.1-flash-lite |
| Judge model | gemini-3.5-flash-lite |
| Answer prompt / judge prompt | answer-v2 / judge-v2 |
| Embedding model | sentence-transformers/all-MiniLM-L6-v2 |
| Questions | 20 |
| Methods | Baseline RAG (k=5), Baseline RAG (k=8), GraphRAG (up to 8 chunks) |
| LLM calls this run (API / cache) | 60 / 60 |

## Metric definitions and limitations

**Deterministic metrics (no LLM involved)**

- **Recall of gold evidence.** Each answerable question has hand-labeled evidence *groups*; a group is met if at least one of its alternative chunks was among the chunks given to the generator. Recall is the fraction of groups met. Limitations: labels are a human's minimal sets, so an equivalent chunk that was not listed counts as a miss; it measures retrieval, not answer quality; the number of chunks differs by method, which is why baseline k=8 is included.
- **Required-term mention rate.** Fraction of required terms (any listed alternative) found, case-insensitively, in the answer summary or claims. Limitations: lexical only; it cannot detect negation or a term used in the wrong context, and it rewards listing.
- **Claims with a valid citation.** Fraction of claims that cite at least one chunk that was actually supplied. Invented chunk or path IDs are counted separately. Limitation: a valid ID does not prove the chunk supports the claim.
- **Abstention accuracy.** The model said the evidence was insufficient exactly when the question is unanswerable.
- **Latency.** Retrieval is wall-clock time. Generation is the duration of the successful API request, excluding client-side rate-limit sleeps and retry waits; cached runs replay the originally measured value. End-to-end is their sum. Limitations: one machine, one run, network variance.

**LLM-judge metrics (a different model from the answerer when configured)**

- **Correctness**, **unsupported or contradicted claims**, and **forbidden claims** are opinions of a language model comparing answers with the human reference answer and the supplied evidence. They are not ground truth. The judge can be lenient or harsh, was not human-verified, and a model grading text from a related model family may be biased.

**Statistics.** The question set is small (20), so there are no significance tests; a difference of one question is within noise. Questions flagged `dev` were used while developing the system and are reported separately from held-out ones.

## Results: all questions

| Metric | Baseline RAG (k=5) | Baseline RAG (k=8) | GraphRAG (up to 8 chunks) |
|---|---|---|---|
| Questions (generation errors) | 20 (0) | 20 (0) | 20 (0) |
| Evidence chunks given to the generator (mean) | 5.0 | 8.0 | 7.8 |
| Recall of gold evidence (answerable questions) | 0.83 | 0.87 | 1.00 |
| Required-term mention rate (deterministic) | 0.89 | 0.92 | 1.00 |
| Claims with a valid citation | 100% | 100% | 100% |
| Invented chunk/path IDs (count) | 0 | 0 | 0 |
| Abstention accuracy | 95% | 100% | 100% |
| Judge: correctness (1 / 0.5 / 0, mean) | 0.95 | 0.97 | 1.00 |
| Judge: claims unsupported or contradicted | 0% | 0% | 0% |
| Judge: questions with a forbidden claim | 0% | 0% | 0% |
| Retrieval latency, median (ms) | 10 | 10 | 12 |
| Generation latency, median (ms) | 2,220 | 2,233 | 2,104 |
| End-to-end latency, median (ms) | 2,230 | 2,243 | 2,116 |

## Results: held-out questions only (17; questions used during development excluded)

| Metric | Baseline RAG (k=5) | Baseline RAG (k=8) | GraphRAG (up to 8 chunks) |
|---|---|---|---|
| Questions (generation errors) | 17 (0) | 17 (0) | 17 (0) |
| Evidence chunks given to the generator (mean) | 5.0 | 8.0 | 7.7 |
| Recall of gold evidence (answerable questions) | 0.85 | 0.90 | 1.00 |
| Required-term mention rate (deterministic) | 0.96 | 0.96 | 1.00 |
| Claims with a valid citation | 100% | 100% | 100% |
| Invented chunk/path IDs (count) | 0 | 0 | 0 |
| Abstention accuracy | 94% | 100% | 100% |
| Judge: correctness (1 / 0.5 / 0, mean) | 0.97 | 1.00 | 1.00 |
| Judge: claims unsupported or contradicted | 0% | 0% | 0% |
| Judge: questions with a forbidden claim | 0% | 0% | 0% |
| Retrieval latency, median (ms) | 10 | 10 | 12 |
| Generation latency, median (ms) | 2,258 | 2,254 | 2,111 |
| End-to-end latency, median (ms) | 2,268 | 2,264 | 2,126 |

## Results by question type (cell = recall / judge correctness)

| Question type | n | Baseline RAG (k=5) | Baseline RAG (k=8) | GraphRAG (up to 8 chunks) |
|---|---|---|---|---|
| direct_fact | 4 | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |
| relationship | 4 | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |
| multi_hop | 4 | 0.60 / 0.75 | 0.60 / 0.88 | 1.00 / 1.00 |
| cross_document | 4 | 0.75 / 1.00 | 0.81 / 1.00 | 1.00 / 1.00 |
| insufficient_evidence | 2 | n/a / 1.00 | n/a / 1.00 | n/a / 1.00 |
| misleading | 2 | 0.75 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |

## Paired comparison (number of questions)

| Comparison | Judge correctness | Recall |
|---|---|---|
| GraphRAG vs Baseline RAG (k=5) | 2 better / 18 same / 0 worse | 6 better / 12 same / 0 worse |
| GraphRAG vs Baseline RAG (k=8) | 1 better / 19 same / 0 worse | 5 better / 13 same / 0 worse |

## Per question (C = correct, P = partially, I = incorrect, R = recall)

| Question | Type | Flag | Baseline RAG (k=5) | Baseline RAG (k=8) | GraphRAG (up to 8 chunks) |
|---|---|---|---|---|---|
| q01 | direct_fact |  | C (R 1.00) | C (R 1.00) | C (R 1.00) |
| q02 | direct_fact |  | C (R 1.00) | C (R 1.00) | C (R 1.00) |
| q03 | direct_fact |  | C (R 1.00) | C (R 1.00) | C (R 1.00) |
| q04 | direct_fact |  | C (R 1.00) | C (R 1.00) | C (R 1.00) |
| q05 | relationship |  | C (R 1.00) | C (R 1.00) | C (R 1.00) |
| q06 | relationship |  | C (R 1.00) | C (R 1.00) | C (R 1.00) |
| q07 | relationship |  | C (R 1.00) | C (R 1.00) | C (R 1.00) |
| q08 | relationship |  | C (R 1.00) | C (R 1.00) | C (R 1.00) |
| q09 | multi_hop | dev | P (R 0.25) | P (R 0.25) | C (R 1.00) |
| q10 | multi_hop |  | P (R 0.50) | C (R 0.50) | C (R 1.00) |
| q11 | multi_hop |  | C (R 0.67) | C (R 0.67) | C (R 1.00) |
| q12 | multi_hop |  | C (R 1.00) | C (R 1.00) | C (R 1.00) |
| q13 | cross_document |  | C (R 1.00) | C (R 1.00) | C (R 1.00) |
| q14 | cross_document |  | C (R 0.50) | C (R 0.75) | C (R 1.00) |
| q15 | cross_document |  | C (R 0.50) | C (R 0.50) | C (R 1.00) |
| q16 | cross_document |  | C (R 1.00) | C (R 1.00) | C (R 1.00) |
| q17 | insufficient_evidence | dev | C | C | C |
| q18 | insufficient_evidence |  | C | C | C |
| q19 | misleading |  | C (R 0.50) | C (R 1.00) | C (R 1.00) |
| q20 | misleading | dev | C (R 1.00) | C (R 1.00) | C (R 1.00) |

## Questions where GraphRAG did worse than baseline k=8

_None on correctness, recall, or forbidden claims._

## Questions where GraphRAG did better than baseline k=8

- **q09** (multi_hop, dev): judge correctness 1.0 vs 0.5; recall 1.00 vs 0.25
- **q10** (multi_hop): recall 1.00 vs 0.50
- **q11** (multi_hop): recall 1.00 vs 0.67
- **q14** (cross_document): recall 1.00 vs 0.75
- **q15** (cross_document): recall 1.00 vs 0.50

## Human-adjudicated correctness (reviewed records only)

_The author graded these records against the reference answers and the documents. They were chosen because methods differed or a judge verdict was doubtful, so they are not a random sample and the numbers should not be generalized._

| Method | Records reviewed | Human mean | Judge mean (same records) | Exact agreement |
|---|---|---|---|---|
| Baseline RAG (k=5) | 4 | 0.75 | 0.75 | 4/4 |
| Baseline RAG (k=8) | 4 | 0.75 | 0.88 | 3/4 |
| GraphRAG (up to 8 chunks) | 4 | 0.88 | 1.00 | 3/4 |

### Judge / human disagreements

- **q10:baseline_k8**: human P, judge C. Omits Invoice Download; the summary states that purchases 'will be affected' with certainty, although the documents do not establish this.
- **q09:graphrag**: human P, judge C. Identifies four downstream features as hedged inferences with appropriate citations; however, the summary omits these features, which appear only in the claims list.
