# Evaluation Results

Benchmark of three local models on a text-to-SQL task against the Chinook
schema. All inference local via Ollama on an M4 Pro (24 GB unified memory),
`temperature = 0` for determinism.

## Method

- **20 questions** across three difficulty tiers: 5 easy (single table), 10
  medium (joins / aggregation), 5 hard (multi-join / subquery / outer join).
- Each question ships with a **canonical SQL** answer (`evals/questions.yaml`),
  verified to execute and return rows.
- A model passes a question only if its query passes the safety layer, executes,
  and its **result set is equivalent** to the canonical's — compared as a
  multiset of rows, ignoring row and column order, with floats rounded. We never
  compare SQL text (two correct queries rarely match textually).
- Latency is per-question LLM generation time; p50/p95 are over the 20 questions.

## Results

| Model | Accuracy | easy | medium | hard | p50 latency | p95 latency |
|-------|----------|------|--------|------|-------------|-------------|
| llama3.1:8b      | **85%** (17/20) | 5/5 | 8/10 | 4/5 | 1580 ms | 2748 ms |
| qwen2.5-coder:7b | 75% (15/20)     | 4/5 | 7/10 | 4/5 | 1566 ms | 2580 ms |
| phi3:mini (3.8B) | 70% (14/20)     | 5/5 | 7/10 | 2/5 | **994 ms** | **1797 ms** |

## Failure-mode analysis

Accuracy alone is misleading; *where* a model fails drives model selection.

**llama3.1:8b** — strongest overall. Its 3 misses were subtle, not broken:
`INNER` vs `LEFT JOIN` on "tracks per playlist" (it included empty playlists),
`GROUP BY name` instead of `id` when summing track revenue (merging tracks that
share a title), and returning a `TrackId` where the question wanted the track
name. All "almost right."

**qwen2.5-coder:7b** — a code-specialized model that, surprisingly, missed an
*easy* question by hallucinating a pluralized table name (`MediaTypes` for
`MediaType`). Its other misses were the same `GROUP BY name` bug and dropping the
aggregate column the canonical answer includes.

**phi3:mini (3.8B)** — the size/accuracy tradeoff, made concrete. ~37% faster
(p50 994 ms) and perfect on easy questions, but it collapsed on the hard tier
(2/5) with failure modes the larger models never showed:
- **Wrong SQL dialect** — emitted T-SQL `SELECT TOP(10) ...` (SQLite has no
  `TOP`), twice.
- **Broke the structured-output contract** — returned JSON that failed Pydantic
  validation (empty `sql`) on one question; the 8B models held the contract on
  all 20.
- **Hallucinated a column** (`Invoice.InvoiceLineId`).

## What the safety layer caught

The `sqlglot` layer's value showed up beyond blocking malicious SQL: it rejected
**real model errors** before they reached the database — qwen's hallucinated
`MediaTypes` table (`UnknownTableError`) and phi3's T-SQL `TOP` syntax (parse
error). Wrong-table and wrong-dialect mistakes are caught as a side effect of the
allowlist + AST validation.

## Caveat: benchmark ambiguity

Two of the recorded failures are arguably question ambiguity, not model error:
whether to include the millisecond value alongside track names (m4), and
`INNER` vs `LEFT JOIN` semantics for "tracks per playlist" (m5). Both model
answers are defensible. This understates true accuracy slightly and is itself a
lesson: result-equivalence is only as good as the precision of the question and
its canonical answer.

## Takeaway

For this workload, **llama3.1:8b** is the pick — highest accuracy with latency
comparable to qwen. **phi3:mini** is a viable choice when latency matters more
than hard-query accuracy. A code-specialized model (qwen) did **not** beat a
general one (llama) here — specialization is not a guarantee.
