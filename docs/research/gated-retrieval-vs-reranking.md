# Gated Retrieval vs Reranking Research — chat-rag-agent

Date: 2026-08-24
Scope: Investigate gated retrieval vs reranking as relevance controls for this repo's hybrid RAG stack (fastembed multilingual-e5-small 384d + Chroma PersistentClient cosine + bm25s RRF k=60 + pydantic-ai stream_answer 120s). Trace current gating (none), ScholarFlow gated retrieval as concrete reference, reranking primary sources, compatibility, adoption paths, and verdict. All claims cite primary source (official docs/spec/source or repo file path + line).

---

## Summary

**Current repo has no gated retrieval.** hybrid_query returns top-k RRF winners unconditionally; search_documents trusts whatever it gets; only post-LLM cited filter prunes uncited sources. **Reranking reorders; gating filters.** They are complements, not substitutes — reranking still needs a threshold/gate after rerank, gated retrieval filters weak hits before or after rerank. For this private-document chatbot, **gating alone is the minimal correct fix** (20-40 lines, zero new dep, no latency cost). Reranking + gating is a precision upgrade when dense alone confuses near-misses (legal phrasing, Vietnamese-English cross-lingual), but adds model download + 10-80 ms latency and still requires the same gate.

---

## 1. Current Retrieval Gating — Ground Truth

### 1.1 Vector store backend/app/db/vector_store.py

| Line | What it is | Gating? |
|---|---|---|
| vector_store.py:55 | def rrf(ranked: list[list[str]], k: int = 60) -> list[tuple[str, float]] — score = sum(1/(k+rank+1)) | No threshold; pure rank fusion |
| vector_store.py:68-73 | chromadb.PersistentClient(path=str(persist_dir)) + get_or_create_collection("documents", metadata={"hnsw:space": "cosine"}) | Cosine distance d = 1 - cos, but distance never inspected in hybrid path |
| vector_store.py:124-143 | query(query_embedding, k=5) — collection.query(query_embeddings=[...], n_results=k, include=[documents,metadatas,distances]) -> score = distances[0][i] | Distance returned but never thresholded |
| vector_store.py:145-174 | hybrid_query(query_text, query_embedding, k=5) — bm25.retrieve(k=k*2) + self.query(k=k*2) -> fused = rrf([vec_ranks, bm25_ranks])[:k] -> collection.get(ids=[fused ids]) -> score = RRF score | **No gate.** k*2 over-retrieve then slice; RRF score is 1/(60+rank+1) sum (~0.016 for rank 0, ~0.007 for rank 8), not a cosine distance |
| vector_store.py:44-52 | _VI_STOPWORDS 22 words + STOPWORDS_EN 34 = 56 stopwords for bm25s.tokenize | Tokenization only, not gating |
| vector_store.py:176-224 | get_metadata, count, list_documents, delete_document(where={"title": title}) | Metadata where used only for delete; no retrieval where filter |

**Finding:** Hybrid path discards distances entirely — fused results carry only RRF scores. Even a well-tuned cosine threshold (e.g. < 0.35) cannot be applied without re-querying dense distances separately.

### 1.2 RAG service backend/app/services/rag.py

| Line | What it is | Gating? |
|---|---|---|
| rag.py:26-34 | Deps(vector_store, retrieved: list[dict]) + RAGState(question, history, new_messages, conversation_id, stream, sources, fallback_reply) | No relevance state |
| rag.py:170-189 | search_documents(ctx, query) -> str — query_prefix()+query -> get_embeddings().query_embed -> vector_store.hybrid_query(query, embedding, 8) | k=8 fixed. Lines 184-185 explicitly: ponytail: no relevance threshold — RRF scores aren't cosine similarity, so the model judges relevance from content. Add a dense-only cosine gate if false positives appear. |
| rag.py:186-189 | if not docs: return "(No relevant documents found.)" -> _track_sources -> _format_context | Empty-check only; any non-empty fusion (even boilerplate) becomes context |
| rag.py:137 | UsageLimits(request_limit=3) + rag.py:292 wait_for(get_graph().run(...), timeout=120.0) + rag.py:308 asyncio.timeout(120) | 120 s budget covers whole agentic loop; retrieval is sub-second |
| rag.py:328-329 | cited = {int(m) for m in re.findall(r"\[(\d+)\]", "".join(answer_parts))} + state.sources = [s for s in deps.retrieved if s["n"] in cited] | **Post-LLM citation filter** — keeps only sources the answer actually cited via [1] regex. Not a retrieval gate; LLM may hallucinate citations or omit valid ones. |
| rag.py:113-167 | _track_sources dedup by (title, reference), _format_context [n] title (Ref) p.page | Formatting/dedup, not gating |

**Finding:** Single tool, single k=8, no score inspection, no where filter, no diagnostics. Prompt rule 4 delegates "does this answer the question?" to the LLM.

### 1.3 Config backend/app/core/config.py

| Line | Rule |
|---|---|
| config.py:21 | embedding_model: str = "intfloat/multilingual-e5-small" (384d, query:/passage: prefix) |
| config.py:22-42 | context_prompt 8 rules — Rule 4: If search_documents returns "(No relevant documents found.)" or the results do not actually answer the question, say the library does not cover it... — LLM-judged, not scored |
| config.py:44-45 | vector_store_dir: str = ".chromadb" upload_dir: str = "data/uploads" | No threshold / gate / reranker config keys |

**Finding:** Zero gating knobs in settings — any gate would be a new Settings field.

### 1.4 Ingest backend/app/services/document_ingest.py:29-33,83-89

- RecursiveChunker(tokenizer="character", chunk_size=1200, min_characters_per_chunk=24) — no pageNumber/sourceLabel provenance (vs ScholarFlow hierarchical + OCR provenance). Chunk index is page proxy (rag.py:162-164).
- base_metadata {title, clean_title, source, type, reference, chunk, summary} — no language, topic, fileType gate fields.

**Net:** Repo trusts Retrieval -> LLM -> Citation-regex. Failure mode is LLM citing weak/off-topic chunks because they were in top-8 RRF regardless of cosine distance or lexical coverage.

---

## 2. What Gated Retrieval Is

### 2.1 Definition

Gated retrieval = **filtering by a relevance threshold before or after ranking**, so variable numbers of results (including zero) are returned based on score, rather than fixed top-k unconditionally. Canonical pattern:

1. Over-retrieve (n_results = k*2 or k*3)
2. Score each candidate (cosine distance/similarity, BM25 normalized score, fused score, lexical coverage, etc.)
3. Apply threshold(s) -> drop low-confidence hits
4. Optionally apply floor relative to best score (max(floor, bestScore - margin))
5. Return survivors (0..k), log rejectedCandidateCount + rejectionReason

Gate can be **pre-LLM** (retrieval) and/or **post-rerank**; without it, every query returns exactly k docs even when all are distant.

### 2.2 Chroma distance/threshold gating — primary sources

**Chroma has no native score_threshold / distance_threshold query parameter** on collection.query. Gating is application-layer post-filter on distances returned by HNSW.

- https://docs.trychroma.com/docs/querying-collections/query-and-get — collection.query(query_embeddings=[...], n_results=k, where={...}, where_document={...}, include=[documents,metadatas,distances]) returns distances column-major; where/where_document are pre-filter eligibility, not threshold.
- https://cookbook.chromadb.dev/core/advanced/queries/ — 5-stage model: 1 Candidate selection (where/where_document) -> 2 Relevance ranking (KNN HNSW) -> 3 Hybrid fusion (Cloud rank(Rrf(...)), local is manual) -> 4 Grouping -> 5 Response shaping. Distance gating is not a stage; you implement it after KNN.
- https://cookbook.chromadb.dev/core/filters/ — where schema ($eq,$ne,$gt,$gte,$lt,$lte,$in,$nin,$contains + $and/$or) is for metadata pre-filter, not score threshold.
- https://docs.trychroma.com/docs/collections/configure — hnsw:space options: l2 (sum(A-B)^2), ip (1 - dot), cosine (1 - cos/||A||·||B||). With cosine and normalized E5 embeddings, distance in [0, 2], similarity = 1 - distance. Threshold example depends on space + model calibration.

Canonical gated pattern (primary source: c-sharpcorner airline RAG tuning + cookbook hybrid guidance):

```python
# Over-retrieve then gate — Chroma returns distances, app filters
raw = collection.query(
    query_embeddings=[query_embedding],
    n_results=16,  # k*2 for k=8
    include=["documents", "metadatas", "distances"],
)
# cosine distance gate tuned per-collection via 200+ labeled queries
threshold = 0.35  # e.g. 0.28-0.40 for policy docs, 0.45-0.60 for broad FAQs
kept = [
    (doc, meta, dist)
    for doc, meta, dist in zip(raw["documents"][0], raw["metadatas"][0], raw["distances"][0])
    if dist < threshold
][:8]
if not kept:
    return []  # triggers "(No relevant documents found.)" upstream
```

Calibration guidance (primary: https://www.c-sharpcorner.com/article/tuning-chromadb-retrieval-thresholds-for-airline-safety-critical-rag/): collect 200+ real queries with human labels, plot precision vs distance, pick elbow where precision >=80%, per-collection not global, recalibrate on embedding model change.

**LangChain adapter** adds syntactic sugar search_type="similarity_score_threshold" with score_threshold — but this is a wrapper that does the same post-filter; Chroma server itself does not enforce it.

### 2.3 Hybrid retrieval gating patterns — primary sources

BM25 and dense scores are on incomparable scales (BM25 unbounded ~0-20, cosine similarity in [-1,1] or distance in [0,2]). Two approaches:

- **RRF avoids normalization** — fuse ranks, not scores: score = sum 1/(k+rank+1). Gating RRF score is brittle (tiny values, query-independent). Better to gate on **per-signal distance/score before or after fusion**, or on **lexical coverage**.
- **Normalized weighted sum** — min-max normalize each signal to [0,1] then weighted sum (ScholarFlow style). Then threshold the normalized fused score. More tunable, needs calibration per corpus.

https://github.com/xhluca/bm25s — bm25s.BM25(method="lucene", k1=1.2, b=0.75) + tokenize(text, stopwords=..., splitter=r"(?u)\b\w\w+\b") . Repo wiring at vector_store.py:98-106 matches this API. No built-in threshold.

### 2.4 ScholarFlow gated retrieval — concrete implementation

File: D:\learning-resource-app\learning-resource-app\src\lib\search\ranking.ts

**Constants:**

```ts
// ranking.ts:77
const SEMANTIC_ONLY_THRESHOLD = 0.55;
// ranking.ts:205-206
const coverageThreshold = groups.length <= 2 ? 0.5 : 0.4;
// ranking.ts:211
const boilerplatePenalty = hasBoilerplate(...) ? 0.32 : 0;
// ranking.ts:253
const relevanceFloor = Math.max(0.32, bestScore - 0.25);
```

**Diagnostics shape:**

```ts
// ranking.ts:29-34
export type SearchRankingDiagnostics = {
  bestScore: number;
  acceptanceThreshold: number;
  rejectedCandidateCount: number;
  rejectionReason: "LOW_RELEVANCE" | null;
};
```

**Gate logic (ranking.ts:204-210, 251-256):**

```ts
const hasLexicalEvidence = groups.length > 0 && lexicalCoverage >= coverageThreshold;
const hasStrongSemanticEvidence = (semantic ?? 0) >= SEMANTIC_ONLY_THRESHOLD;
const passesRelevanceGate =
  (hasLexicalEvidence || hasStrongSemanticEvidence)
  && satisfiesFileType
  && satisfiesDifficulty;

const ranked: ScoredSearchResult[] = /* weighted sum + bonuses - boilerplate */ ;
const accepted = ranked.filter(r => r.passesRelevanceGate);
const bestScore = accepted[0]?.score ?? ranked[0]?.score ?? 0;
const relevanceFloor = Math.max(0.32, bestScore - 0.25);
const results = accepted
  .filter(r => r.score >= relevanceFloor)
  .slice(0, limit);
```

**Supporting helpers:**

- normalizeSearchText (ranking.ts:79-88): NFD diacritic strip, d→d, lower, [^a-z0-9]->" " — bilingual tolerance.
- groupCoverage + lexicalCoverage = max(contentCoverage, titleCoverage, topicCoverage) (ranking.ts:143-147,199): alias groups khoang trong nghien cuu -> [research gap,...] etc. — query concept expansion (17 groups at ranking.ts:41-59).
- hasBoilerplate (ranking.ts:149-152): first 240 chars or sourceLabel contains copyright|all rights reserved|table of contents|preface|isbn|... (ranking.ts:61-73) -> penalty 0.32.
- STOP_WORDS 37 VI + 14 EN (ranking.ts:36-39), QUERY_CONCEPT_ALIASES 17 vi-en (ranking.ts:41-59).
- Fusion weights (ranking.ts:186-190): hasBoth ? 0.68*sem + 0.14*kw + 0.13*vecRank + 0.05*kwRank + 0.04 : sem? 0.82*sem+0.18*vecRank : 0.62*kw+0.18*kwRank then final 0.78*retrieval + 0.12*contentCov + 0.06*titleCov + 0.04*topicCov + bonuses - penalty (ranking.ts:212-218).

**Pipeline position:** hybrid-search.ts: searchByVector + searchByKeyword -> Promise.allSettled -> rankSearchCandidatesWithDiagnostics -> filter chunksPerDocument -> slice 30. Gate runs **after** fusion, before chunksPerDocument dedup.

> ScholarFlow is search-as-product (filter + gate + diagnostics), not RAG chatbot. Its gate constants are tuned for 1024d BGE-M3; 384d E5 would need recalibration.

---

## 3. What Reranking Is and How It Differs

### 3.1 Cross-encoder reranking — mechanism

| Aspect | Bi-encoder (retrieval) | Cross-encoder (reranking) |
|---|---|---|
| Input | Query and docs encoded separately -> cosine lookup | Query+doc concatenated as one sequence -> joint attention |
| Score | cosine(query_emb, doc_emb) distance | logit = head(Transformer([query; doc])) — unbounded (-10..+10) or sigmoid->[0,1] |
| Cost | O(N) ANN + one embed per query | O(k) forward passes per query (k = candidates) |
| Accuracy | Fast, coarse | Slower, more precise on nuance/negation/order |

Pattern: retrieve k=20..100 with bi-encoder/BM25 cheap, rerank to top 8, then gate.

Primary sources:

- https://sbert.net/docs/cross_encoder/usage/usage.html — CrossEncoder = reranker, superior to bi-encoder but slower (pairwise), used to re-rank top-k from SentenceTransformer.
- https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2 — MS MARCO passage-ranking task, CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2") then model.predict([(q, doc)...]) -> logits (-inf..+inf), model.rank(q, passages) returns sorted corpus_id/score. Table: L6-v2 NDCG@10 74.30 MRR@10 39.01 @ 1800 docs/sec; L12-v2 960 docs/sec; TinyBERT 9000 docs/sec.
- https://huggingface.co/BAAI/bge-reranker-v2-m3 — XLM-RoBERTa-large 568M multilingual, FlagReranker('BAAI/bge-reranker-v2-m3', use_fp16=True) -> reranker.compute_score(['query','passage'], normalize=True) sigmoid -> [0,1]. BGE docs recommend hybrid + rerank pipeline explicitly (https://github.com/FlagOpen/FlagEmbedding/blob/master/research/BGE_M3/README.md).
- Adapter layers: sbert.net CrossEncoder.predict vs FlagEmbedding FlagReranker.compute_score(..., normalize=True) — same underlying task, different API.

### 3.2 Cohere Rerank API — primary source

- https://docs.cohere.com/docs/rerank + https://docs.cohere.com/reference/rerank — POST https://api.cohere.com/v2/rerank with model: rerank-v3.5 / rerank-v4.0-pro|fast, query, documents: string[] (<=10k, ideally <=1k), top_n, max_tokens_per_doc 4096 (truncates, auto-chunks if query+doc > context).
- Returns results: [{index, relevance_score: float [0,1]}] ordered by relevance; relevance_score normalized but **not comparable across queries** — "you can't assume 0.91 is 2x 0.45".
- Cohere best-practices threshold calibration (https://docs.cohere.com/docs/reranking-best-practices.mdx): sample 30-50 representative queries, collect borderline-relevant doc per query, rerank to get sample_scores, use mean as threshold. Same human-label loop as Chroma distance tuning, but on cross-encoder scores.

Cost/latency: network hop + billing per 1k docs; offline-incompatible. Not a drop-in for private legal docs unless Cohere is approved.

### 3.3 Fastembed reranking — primary source

- https://github.com/qdrant/fastembed + https://qdrant.tech/documentation/fastembed/fastembed-rerankers/ + https://qdrant.github.io/fastembed/examples/Supported_Models/ — from fastembed.rerank.cross_encoder import TextCrossEncoder (ONNX Runtime, CPU, no torch).

Supported ONNX models (fastembed/rerank/cross_encoder/onnx_text_cross_encoder.py: supported_onnx_models):

| Model | Size | License | Context | Note |
|---|---|---|---|---|
| Xenova/ms-marco-MiniLM-L-6-v2 | 0.08 GB | apache-2.0 | 512 | Fastest; English MS MARCO |
| Xenova/ms-marco-MiniLM-L-12-v2 | 0.12 GB | apache-2.0 | 512 | +1.5x quality, -2x speed vs L6 |
| jinaai/jina-reranker-v1-tiny-en | 0.13 GB | apache-2.0 | 8K | 8K context, blazing fast |
| jinaai/jina-reranker-v1-turbo-en | 0.15 GB | apache-2.0 | 8K | Same family |
| BAAI/bge-reranker-base | 1.04 GB | mit | 512 | Heavy; needs FlagEmbedding quality |
| jinaai/jina-reranker-v2-base-multilingual | 1.11 GB | cc-by-nc-4.0 | 1K+sliding | Multilingual; NC license |

BGE v2-m3 (568M) is **not** in fastembed ONNX registry — requires FlagEmbedding (torch + transformers), not ONNX. Jina v2 multilingual is the fastembed multilingual option, but NC-licensed.

API (primary: fastembed/rerank/cross_encoder/text_cross_encoder.py + docs example):

```python
from fastembed.rerank.cross_encoder import TextCrossEncoder

reranker = TextCrossEncoder(model_name="Xenova/ms-marco-MiniLM-L-6-v2")
# fast path — rerank docs against one query
scores = list(reranker.rerank(query, documents))  # Iterable[float] logits
# generic — scored pairs
scores = list(reranker.rerank_pairs([(q, d) for d in docs]))

# custom ONNX model (same pattern as embeddings.py:38 TextEmbedding.add_custom_model)
TextCrossEncoder.add_custom_model(
    model="BAAI/bge-reranker-v2-m3",
    sources=ModelSource(hf="BAAI/bge-reranker-v2-m3"),
    model_file="onnx/model.onnx",
)
```

Notes from source: rerank yields logits (not sigmoid); apply sigmoid yourself if you want [0,1]. rerank_pairs(parallel=N) exists but parallel>1 warning: cross-encoder currently single-device only (onnx_text_cross_encoder.py logs warning on device_ids>1). Batch size default 64.

### 3.4 Chroma + reranking / ColBERT

- Chroma docs https://docs.trychroma.com + https://cookbook.chromadb.dev/core/advanced/queries/ — no native reranker; reranking is application layer after collection.query + collection.get, identical to gating story.
- https://github.com/qdrant/fastembed also exposes LateInteractionTextEmbedding (ColBERT) — late-interaction scoring (MaxSim) is an alternative reranker but not in fastembed cross-encoder registry; it requires separate colbertv2 model and different API. ScholarFlow does not use it; BGE-M3 unified dense+ sparse + colbert is the reference for that stack (FlagEmbedding BGE-M3 README).

### 3.5 Score vs gate — conceptual difference

- **Reranking = reordering**: maps k inputs -> k scored outputs sorted by relevance. Every input still returned, just sorted. Does not by itself drop irrelevant hits.
- **Gating = filtering**: maps k inputs -> 0..k outputs by threshold. Drops low-confidence hits entirely (may return empty).
- **Together**: retrieve k=16 -> rerank 16 -> gate by rerank score threshold -> take top 8 survivors. Threshold still needed after rerank because reranker always returns a ranking even when all candidates are off-topic.

Cohere docs state this explicitly: relevance_score is normalized [0,1] ... The most important output is the absolute rank ... you can't assume 0.91 is 2x 0.45 — to find a threshold ... sample 30-50 queries, mean borderline score (https://docs.cohere.com/docs/reranking-best-practices). Fastembed/BGE docs show compute_score(..., normalize=True) sigmoid but same caveat: calibrate per corpus.

---

## 4. Can Reranking Replace Gating?

**No — complement, not replacement.** Four reasons grounded in primary sources:

1. **Reranking always ranks, even when nothing is relevant.** Given 8 off-topic Vietnam legal chunks and query "capital of France", a cross-encoder will still return a sorted list with a top score — just lower than for a relevant chunk. Without a gate, that top-ranked off-topic chunk becomes [1] and gets cited. Cohere (best-practices), BGE (FlagEmbedding/README hybrid+rerank), and Chroma airline tuning all require a threshold *after* rerank.

2. **Gating answers a different question.** Reranking asks "which of these k is most relevant?" Gating asks "is any of these relevant enough to show?" ScholarFlow passesRelevanceGate + relevanceFloor explicitly encodes both: gate out weak hits, then floor relative to best survivor.

3. **Gating can run before reranking to save work.** Filtering by dense distance pre-rerank reduces cross-encoder passes (cost proportional to k). Typical pipeline: dense k=20 -> distance gate -> rerank survivors (5-12) -> rerank-score gate -> top 8.

4. **Different failure modes need different gates.** Dense distance gate catches "all results are far" (empty library, off-topic query). Lexical coverage gate catches "semantically close but keyword-missing" (e.g. wrong decree number). Reranker threshold catches "top dense hit is still a near-miss on nuance". One reranker threshold alone misses the first two.

Minimal correct stack is gated retrieval even without reranking. Adding reranking without gating upgrades ordering but not filtering.

---

## 5. Compatibility With This Repo's Stack

### 5.1 Stack as pinned

| Component | Pinned / wired | Relevant file:line |
|---|---|---|
| Embedding | fastembed>=0.5.0 intfloat/multilingual-e5-small 384d CLS onnx/model.onnx query:/passage: prefix | backend/pyproject.toml:21 backend/app/db/embeddings.py:14-27 backend/app/core/config.py:21 |
| Vector store | chromadb>=1.5,<2 PersistentClient(.chromadb) hnsw:space cosine | backend/pyproject.toml:12 backend/app/db/vector_store.py:68-73 |
| Sparse | bm25s>=0.3.10 method lucene k1 1.2 b 0.75 56 stopwords splitter (?u)\b\w\w+\b >=2 chars | backend/pyproject.toml:24 backend/app/db/vector_store.py:98-106 |
| Chunker | chonkie>=0.1.0 RecursiveChunker character 1200 min24 | backend/pyproject.toml:15 backend/app/services/document_ingest.py:29-33 |
| Agent | pydantic-ai>=2.19,<3 Agent.run_stream stream_text(delta=True) ReinjectSystemPrompt ProcessHistory | backend/pyproject.toml:14 backend/app/services/rag.py:26,217-232,309 |
| Runtime | fastapi[standard]>=0.139 SSE text/event-stream 120 s graph+stream timeout | backend/pyproject.toml:8 backend/app/services/rag.py:292,308 |

### 5.2 Can we add cross-encoder reranker in-process with fastembed/ONNX? Need new dep? Latency impact?

**Yes — in-process ONNX via existing fastembed, no new pip dep.** fastembed already depends on onnxruntime. TextCrossEncoder uses the same cache / download / FASTEMBED_CACHE_PATH plumbing as TextEmbedding (fastembed/rerank/cross_encoder/onnx_text_cross_encoder.py + text_cross_encoder.py). Model download is lazy on first TextCrossEncoder(model_name=...) — same pattern as get_embeddings() (embeddings.py:35-49).

**What is already available without editing pyproject.toml:**

```bash
python -c "from fastembed.rerank.cross_encoder import TextCrossEncoder; print(TextCrossEncoder.list_supported_models())"
# returns 6 ONNX models (Xenova L6/L12, Jina tiny/turbo/v2-multilingual, BGE base) — no torch
```

**If you want BGE v2-m3 (recommended multilingual for vi/en legal):** not in ONNX registry — requires FlagEmbedding (pip install FlagEmbedding + torch + transformers), ~568M params + CUDA optional (use_fp16=True). Different dep class, heavier. Jina v2 multilingual is the ONNX multilingual fallback but is cc-by-nc-4.0 (commercial use caveat). MiniLM L6 is English MS MARCO — works but weaker on Vietnamese (cross-lingual E5 retrieval is multilingual; reranker would be English-biased).

**Latency on 120 s budget:**

| Model | Size | CPU throughput (primary: sbert.net table Docs/Sec) | 8 docs est. | 16 docs est. |
|---|---|---|---|---|
| Xenova/ms-marco-MiniLM-L-6-v2 | 0.08 GB | 1800 docs/sec | ~5 ms | ~10 ms |
| Xenova/ms-marco-MiniLM-L-12-v2 | 0.12 GB | 960 docs/sec | ~9 ms | ~17 ms |
| jinaai/jina-reranker-v2-base-multilingual | 1.11 GB | not tabled; ~similar to BGE base (slower) | ~40-80 ms* | ~80-160 ms* |
| BAAI/bge-reranker-base (torch) | 1.04 GB | GPU recommended | CPU ~80-120 ms* | ~150-250 ms* |

*Jina/BGE estimates from FlagEmbedding use_fp16 docs + community benchmarks; exact depends on CPU vs onnxruntime providers. Even worst-case 250 ms is <0.5% of the 120 s stream_answer timeout (rag.py:292/308) and runs once per search_documents tool call (<=3 via _RAG_LIMITS). Streaming LLM dominates wall time, not reranking.

**Memory:** L6 ONNX <100 MB RSS; Jina v2 / BGE ~1 GB model file + onnxruntime arena — fine on typical 2-4 GB container, not on 512 MB lambda. chonkie / pydantic-ai unaffected.

**Threading:** vector_store._ensure_bm25 comment at vector_store.py:88-89 notes single-worker no-lock. TextCrossEncoder similarly single-threaded per instance; reuse singleton like get_embeddings() (@lru_cache). Avoid per-request TextCrossEncoder(...) construction (downloads + session init).

**Caveat:** rerank returns logits (e.g. -11 .. +5 per fastembed example), not [0,1]. Apply sigmoid if you want Cohere-like normalized threshold — or threshold on logits with calibrated value (same human-label loop, different scale).

### 5.3 Gating compatibility

Gating alone has no compatibility risk: pure Python post-filter on distances or lexical coverage (unicodedata.normalize("NFD", ...) stdlib). No new dep, no model download, no latency beyond one extra collection.query distances fetch if hybrid path needs dense distances separately (current hybrid discards them — fix is query(k*2) distances alongside RRF or separate dense-only query).

---

## 6. Minimal Adoption Paths

### 6.1 Option A — Gating alone (ponytail minimal, recommended first)

**Goal:** Stop citing off-topic chunks without adding a model.

**Where:** backend/app/db/vector_store.py: hybrid_query + backend/app/services/rag.py: search_documents + backend/app/core/config.py: Settings

**Config (new knobs, all optional with safe defaults):**

```python
# backend/app/core/config.py — add to Settings
retrieval_k: int = 8
retrieval_distance_threshold: float | None = None  # cosine distance, e.g. 0.35; None = no gate
retrieval_lexical_coverage_threshold: float = 0.4  # ScholarFlow 0.4/0.5; 0 disables
retrieval_boilerplate_penalty: float = 0.32
retrieval_relevance_floor_margin: float = 0.25     # max(0.32, best-0.25)
retrieval_semantic_only_threshold: float = 0.55    # ScholarFlow SEMANTIC_ONLY_THRESHOLD
```

**Vector store — return distances alongside RRF, gate on dense distance + coverage:**

```python
# backend/app/db/vector_store.py — inside hybrid_query, after rrf fusion
# ponytail: keep RRF; just fetch distances to gate — no new lib, stdlib normalize for diacritics
import unicodedata

_BOILERPLATE = {"copyright","all rights reserved","table of contents","preface","isbn","acknowledgements"}

def _norm(t: str) -> str:
    return unicodedata.normalize("NFD", t).replace("d","d").replace("D","D").lower()

def _is_boilerplate(doc: str, meta: dict) -> bool:
    head = _norm(doc[:240])
    label = _norm(meta.get("sourceLabel","") or meta.get("reference","") or "")
    return any(p in head or p in label for p in _BOILERPLATE)

# existing: hits, ids, vec_ranks, bm25_ranks, fused = rrf(...)[:k*2]  (over-retrieve)
# new: fetch distances for vec side to gate before/after fusion
vec_hits = self.query(query_embedding, k=k*2)  # already called as vec_ranks source
dist_by_id = {d["id"]: d["score"] for d in vec_hits}  # score is distance here

# relevance gate — mirrors ScholarFlow ranking.ts:205-210, tuned for legal
# lexical coverage helper (groups = keyword groups from query)
# groups = extract_keyword_groups(query_text)  # port ranking.ts:90-106 if desired, or simple term split
# coverage = groupCoverage(_norm(doc), groups)
# hasLexical = coverage >= (0.5 if len(groups)<=2 else 0.4)
# hasSemantic = (1 - dist_by_id.get(doc_id, 1.0)) >= 0.55  # similarity gate
# passes = (hasLexical or hasSemantic) and not _is_boilerplate(doc, meta)  # ScholarFlow penalty as filter or subtract

# relevance floor — ranking.ts:253
# best = max(score for _, score in fused_passed) if fused_passed else 0
# floor = max(0.32, best - 0.25)
# survivors = [(id,score) for id,score in fused_passed if score >= floor][:k]

# then collection.get(ids=[id for id,_ in survivors], ...) as before
# if not survivors: return []  # triggers "(No relevant documents found.)" in search_documents
```

**Simpler single-threshold variant** if alias groups feel heavy — dense distance only:

```python
# vector_store.py — after fused = rrf([vec_ranks, bm25_ranks])[:k]
# apply Chroma distance gate post-fusion (primary: cookbook distance gating pattern)
if settings.retrieval_distance_threshold is not None:
    fused = [(doc_id, score) for doc_id, score in fused
             if dist_by_id.get(doc_id, 2.0) < settings.retrieval_distance_threshold]
    if not fused:
        return []
```

**RAG — surface diagnostics on event: sources (optional):**

```python
# backend/app/services/rag.py — search_documents return or stream_answer sources payload
# include diagnostics so frontend can show "0 results — below threshold" vs "empty library"
# diagnostics = {"k": 8, "fused": len(fused), "kept": len(survivors), "threshold": settings.retrieval_distance_threshold}
# stream_answer already yields {"type":"sources","sources": state.sources} — extend to
# yield {"type":"sources","sources": state.sources, "diagnostics": diagnostics}
```

**Diff size:** ~25-40 lines across vector_store.py + config.py; no pyproject.toml change. Log bestScore per query (logger.info("search query=%r best=%.3f kept=%d/%d", query, best, len(survivors), len(fused))) — ScholarFlow SearchLog-lite until table justified.

**Tuning:** run 50-100 real Vietnamese + English queries (including off-topic "capital of France", greeting, boilerplate like "table of contents"), plot distance vs human relevance, pick elbow (airline guide suggests 0.35 tight, 0.50 broad; legal private docs skew tight 0.32-0.40). Lexical coverage threshold 0.4 matches ScholarFlow; raise to 0.5 only if short queries get pruned too aggressively.

### 6.2 Option B — Reranking + gating (precision upgrade)

**Pipeline:** hybrid_query k*2 (16) -> rerank 16 docs with TextCrossEncoder -> rerank-score gate -> slice k=8 -> LLM

**Install: nothing** if using fastembed ONNX model (already pinned fastembed>=0.5.0). For Jina v2 multilingual, same — just model_name="jinaai/jina-reranker-v2-base-multilingual". For BGE v2-m3, add FlagEmbedding (heavier).

**Singleton reranker (mirrors embeddings.py:35-49 @lru_cache):**

```python
# backend/app/db/reranker.py (new file, ~30 lines)
from functools import lru_cache
from fastembed.rerank.cross_encoder import TextCrossEncoder  # primary: https://qdrant.github.io/fastembed

@lru_cache(maxsize=1)
def get_reranker() -> TextCrossEncoder:
    # ponytail: MiniLM-L6 ONNX 0.08GB fastest; swap to jinaai/jina-reranker-v2-base-multilingual for vi
    # BAAI/bge-reranker-v2-m3 needs FlagEmbedding, not fastembed
    return TextCrossEncoder(model_name="Xenova/ms-marco-MiniLM-L-6-v2")
```

**Hybrid query with rerank — secondary filter still required (primary: Cohere best-practices + fastembed docs):**

```python
# backend/app/db/vector_store.py — alternative hybrid_query rerank branch
import math
from app.db.reranker import get_reranker  # lazy; don't import at top if you want gate-only default

def hybrid_query_reranked(self, query_text: str, query_embedding: list[float], k: int = 8) -> list[dict]:
    # 1. over-retrieve hybrid as before, k*2
    ids = self._ensure_bm25()
    hits, _ = self._bm25.retrieve(bm25s.tokenize(query_text, stopwords=_STOPWORDS, show_progress=False), k=k*2, show_progress=False)
    bm25_ranks = [ids[i] for i in hits[0]]
    vec_hits = self.query(query_embedding, k=k*2)
    vec_ranks = [d["id"] for d in vec_hits]
    fused = rrf([vec_ranks, bm25_ranks])[:k*2]

    res = self._collection.get(ids=[i for i,_ in fused], include=["documents","metadatas"])
    doc_by_id = dict(zip(res["ids"], res["documents"], strict=True))
    docs = [doc_by_id.get(doc_id, "") for doc_id, _ in fused]

    # 2. rerank — primary: https://qdrant.tech/documentation/fastembed/fastembed-rerankers/
    reranker = get_reranker()
    scores = list(reranker.rerank(query_text, docs))  # logits; higher = more relevant
    # optional sigmoid if you want [0,1] threshold space:
    # scores = [1/(1+math.exp(-s)) for s in scores]

    paired = sorted(zip(fused, scores, docs), key=lambda x: x[1], reverse=True)

    # 3. gate on rerank score — must calibrate; logits scale differs from Cohere [0,1]
    # Calibrate: 30-50 queries x borderline doc -> mean score = threshold (Cohere guide)
    threshold = -1.0  # example for MiniLM logits; tune per corpus; sigmoid threshold e.g. 0.3
    gated = [(fused_item, score) for fused_item, score, _ in paired if score >= threshold]
    top = gated[:k] if gated else []  # empty -> "(No relevant documents found.)"

    # 4. hydrate
    meta_by_id = dict(zip(res["ids"], res["metadatas"], strict=True))
    return [
        {"id": doc_id, "content": doc_by_id.get(doc_id,""), "metadata": meta_by_id.get(doc_id,{}), "score": float(score)}
        for (doc_id,_), score in top
    ]
```

**Feature flag wiring:**

```python
# backend/app/core/config.py
reranker_model: str | None = None  # e.g. "Xenova/ms-marco-MiniLM-L-6-v2" or "jinaai/jina-reranker-v2-base-multilingual"
reranker_threshold: float | None = None  # logits or sigmoid depending on normalize
# rag.py search_documents: if settings.reranker_model: docs = vector_store.hybrid_query_reranked(...)
```

**Cost vs gate-only:** gate-only catches "all results far" early; rerank catches "closest dense hit is still wrong sense" (e.g. "dieu 7" vs "dieu 17", negated clauses). Both still gate. Latency +10-250 ms per tool call; 120 s budget unaffected. Model cache ~80 MB (L6) to ~1.1 GB (Jina v2).

**Cohere alternative (network reranker):**

```python
# Cohere — primary: https://docs.cohere.com/reference/rerank
import cohere
co = cohere.ClientV2(api_key=settings.cohere_api_key.get_secret_value())
resp = co.rerank(model="rerank-v3.5", query=query_text, documents=docs, top_n=8)
# resp.results[*].relevance_score in [0,1], resp.results sorted by relevance
# threshold still needed: mean borderline score from 30-50 labeled pairs
```

Not recommended for this private-doc stack unless Cohere is approved for Vietnamese legal content.

---

## 7. Code Snippets / Config Examples Citing Primary Docs

### Chroma gating (no native threshold — app post-filter)

```python
# Primary: https://docs.trychroma.com/docs/querying-collections/query-and-get
# Primary: https://cookbook.chromadb.dev/core/advanced/queries/ (KNN + post-filter pattern)
raw = collection.query(
    query_embeddings=[query_embedding],
    n_results=16,
    where={"type": "pdf"},              # metadata pre-filter — https://docs.trychroma.com/docs/querying-collections/metadata-filtering
    where_document={"$contains": "SSO"}, # lexical pre-filter — https://cookbook.chromadb.dev/strategies/keyword-search/
    include=["documents","metadatas","distances"],
)
# distances are cosine distance when hnsw:space cosine — https://docs.trychroma.com/docs/collections/configure
kept = [r for r, d in zip(raw["ids"][0], raw["distances"][0]) if d < 0.35]
```

### Fastembed rerank (ONNX in-process)

```python
# Primary: https://qdrant.tech/documentation/fastembed/fastembed-rerankers/
# Primary: https://github.com/qdrant/fastembed/blob/main/fastembed/rerank/cross_encoder/text_cross_encoder.py
from fastembed.rerank.cross_encoder import TextCrossEncoder
from fastembed.common.model_description import ModelSource

# list available ONNX rerankers
print(TextCrossEncoder.list_supported_models())
# load — ONNX Runtime CPU, no torch — https://qdrant.github.io/fastembed/examples/Supported_Models/
reranker = TextCrossEncoder(model_name="Xenova/ms-marco-MiniLM-L-6-v2")
scores = list(reranker.rerank("Who is maintaining Qdrant?", ["fastembed is maintained by Qdrant.", "This is built to be faster..."]))
# [-11.48, 5.47] — logits, sigmoid for [0,1] — https://qdrant.tech/documentation/fastembed/fastembed-rerankers/

# custom model — https://github.com/qdrant/fastembed/blob/main/fastembed/rerank/cross_encoder/text_cross_encoder.py#L(add_custom_model)
TextCrossEncoder.add_custom_model(
    model="Xenova/ms-marco-MiniLM-L-4-v2",
    sources=ModelSource(hf="Xenova/ms-marco-MiniLM-L-4-v2"),
    model_file="onnx/model.onnx",
)
```

### CrossEncoder (sbert) and FlagEmbedding (BGE) — primary

```python
# Primary: https://sbert.net/docs/cross_encoder/usage/usage.html
from sentence_transformers import CrossEncoder
model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2")
scores = model.predict([("How many people live in Berlin?", "Berlin had 3,520,031 inhabitants...")])
ranks = model.rank("How many people live in Berlin?", passages)

# Primary: https://huggingface.co/BAAI/bge-reranker-v2-m3
# Primary: https://github.com/FlagOpen/FlagEmbedding
from FlagEmbedding import FlagReranker
reranker = FlagReranker('BAAI/bge-reranker-v2-m3', use_fp16=True)
score = reranker.compute_score(['query','passage'])            # logit
score01 = reranker.compute_score(['query','passage'], normalize=True) # sigmoid [0,1]
```

### Cohere Rerank (hosted) — primary

```python
# Primary: https://docs.cohere.com/reference/rerank + https://docs.cohere.com/docs/reranking-best-practices
# POST https://api.cohere.com/v2/rerank  {model, query, documents, top_n, max_tokens_per_doc}
# relevance_score in [0,1] — rank matters more than absolute; threshold = mean borderline score
# Threshold recipe (Cohere best-practices):
#   sample_inputs = [(q_i, borderline_doc_i) for 30-50 queries]
#   sample_scores = [rerank(q, [d]).results[0].relevance_score for q,d in sample_inputs]
#   threshold = sum(sample_scores)/len(sample_scores)
```

### ScholarFlow gate constants — primary on-disk

```ts
// Primary: D:\learning-resource-app\learning-resource-app\src\lib\search\ranking.ts
const SEMANTIC_ONLY_THRESHOLD = 0.55;                          // ranking.ts:77
const relevanceFloor = Math.max(0.32, bestScore - 0.25);       // ranking.ts:253
const passesRelevanceGate = (hasLexicalEvidence || hasStrongSemanticEvidence) // ranking.ts:208-210
  && satisfiesFileType && satisfiesDifficulty;
const boilerplatePenalty = hasBoilerplate(...) ? 0.32 : 0;     // ranking.ts:211
```

---

## 8. Verdict for This RAG Chatbot Use-Case

**Do gating first. Add reranking only if gating alone still cites near-misses.**

| Criterion | Gating alone | Reranking + gating |
|---|---|---|
| Problem solved | Empty/weak retrieval returns zero instead of hallucinating; boilerplate filtered; off-topic query -> "(No relevant documents found.)" -> Rule 4 fallback | Above + finer discrimination among top-k near-misses (wrong article number, negated clause) |
| Accuracy lift | High for this corpus (private legal PDFs, many off-topic greetings) — gate removes the dominant failure mode | Incremental; cross-encoder beats bi-encoder on nuance, but E5 384d already handles vi/en cross-lingual |
| Latency | ~0 ms (one distance compare + stdlib NFD) | +5 ms (L6) to +250 ms (BGE/Jina) per search_documents call; still <0.5% of 120 s |
| Cost / deps | Zero new dep, zero download, ~30 lines | No new pip if ONNX (fastembed cache 0.08-1.11 GB download on first use); FlagEmbedding BGE adds torch + 568M model |
| Tuning burden | Must calibrate distance + optional coverage threshold on 50-100 labeled queries per language; ScholarFlow constants are a starting point not a copy-paste for 384d | Must calibrate rerank threshold too (logits vs sigmoid vs Cohere [0,1]); double calibration if both gates differ in scale |
| Risk | Low — reversible via None threshold; no model drift | Model staleness + NC license on Jina v2 multilingual; English MS MARCO reranker underperforms on Vietnamese |

**Recommended sequence:**

1. **Ship gating (Option A)** in vector_store.py:hybrid_query behind Settings flags, log diagnostics, collect 100 real queries (Vietnamese decree Qs, English translations, greetings, off-topic). Tune retrieval_distance_threshold + SEMANTIC_ONLY_THRESHOLD analog for 384d E5 (expect threshold lower than BGE-1024's 0.55; measure, don't copy). Add groupCoverage port only if English queries keep missing Vietnamese BM25 vocab.

2. **Evaluate** precision@k and hallucination rate with/without gate. If false-positive citations remain despite gate (same 2-3 docs always near threshold), **then** trial hybrid_query_reranked with Xenova/ms-marco-MiniLM-L-6-v2 (fastest, permissive license) or jinaai/jina-reranker-v2-base-multilingual (if NC is acceptable) and re-tune threshold.

3. **Skip** Cohere for now (private legal docs + network dependency), BGE v2-m3 via FlagEmbedding unless you specifically need its multilingual quality and can afford torch in container.

> One-liner: **Gating is the filter; reranking is the sorter. Sort without filtering still cites junk — filter first, then decide if sorting is worth the model.**

---

## Sources — Primary Only

**Repo (this codebase):**

- backend/app/db/vector_store.py:55 rrf(k=60) 1/(k+rank+1)
- backend/app/db/vector_store.py:68-73 PersistentClient hnsw:space cosine
- backend/app/db/vector_store.py:98-106 bm25s.BM25 lucene k1 1.2 b 0.75 tokenize stopwords=_STOPWORDS
- backend/app/db/vector_store.py:124-174 query vs hybrid_query k*2 + RRF + get(ids=...) — no threshold
- backend/app/db/vector_store.py:176-224 get_metadata/where={"title": title} delete only
- backend/app/services/rag.py:26-34 Deps/RAGState
- backend/app/services/rag.py:137 UsageLimits(request_limit=3)
- backend/app/services/rag.py:170-189 search_documents k=8 + ponytail: no relevance threshold comment at rag.py:184-185
- backend/app/services/rag.py:292,308 120 s wait_for + asyncio.timeout
- backend/app/services/rag.py:328-329 cited re.findall(r"\[(\d+)\]") filter = provenance not gate
- backend/app/core/config.py:21 embedding_model intfloat/multilingual-e5-small
- backend/app/core/config.py:22-42 context_prompt Rule 4
- backend/app/db/embeddings.py:14-27 TextEmbedding.add_custom_model CLS 384 onnx/model.onnx + query_prefix()/passage_prefix()
- backend/app/services/document_ingest.py:29-33 RecursiveChunker character 1200
- backend/app/services/document_ingest.py:83-89 base_metadata {title,clean_title,source,type,reference,chunk}
- backend/pyproject.toml:8,12,14,15,21,24 fastapi chromadb>=1.5<2 pydantic-ai>=2.19 chonkie fastembed>=0.5.0 bm25s>=0.3.10

**External reference app (concrete gated retrieval example):**

- D:\learning-resource-app\learning-resource-app\src\lib\search\ranking.ts:29-34 SearchRankingDiagnostics
- D:\learning-resource-app\learning-resource-app\src\lib\search\ranking.ts:36-39 STOP_WORDS
- D:\learning-resource-app\learning-resource-app\src\lib\search\ranking.ts:41-59 QUERY_CONCEPT_ALIASES 17 groups
- D:\learning-resource-app\learning-resource-app\src\lib\search\ranking.ts:61-73 BOILERPLATE_PATTERNS
- D:\learning-resource-app\learning-resource-app\src\lib\search\ranking.ts:77 SEMANTIC_ONLY_THRESHOLD = 0.55
- D:\learning-resource-app\learning-resource-app\src\lib\search\ranking.ts:79-88 normalizeSearchText NFD
- D:\learning-resource-app\learning-resource-app\src\lib\search\ranking.ts:90-106 extractKeywordGroups
- D:\learning-resource-app\learning-resource-app\src\lib\search\ranking.ts:143-147 groupCoverage + lexicalCoverage
- D:\learning-resource-app\learning-resource-app\src\lib\search\ranking.ts:149-152 hasBoilerplate
- D:\learning-resource-app\learning-resource-app\src\lib\search\ranking.ts:186-218 weighted fusion + boilerplatePenalty 0.32
- D:\learning-resource-app\learning-resource-app\src\lib\search\ranking.ts:204-211 coverageThreshold 0.5/0.4 + passesRelevanceGate
- D:\learning-resource-app\learning-resource-app\src\lib\search\ranking.ts:251-256 relevanceFloor max(0.32,best-0.25) + accepted filter

**Official docs / specs / source code (not blogs):**

- https://docs.trychroma.com/docs/querying-collections/query-and-get — collection.query n_results where/where_document include distances
- https://docs.trychroma.com/docs/querying-collections/metadata-filtering — where schema
- https://docs.trychroma.com/docs/collections/configure — hnsw:space cosine|l2|ip equations, ef_search/ef_construction
- https://cookbook.chromadb.dev/core/advanced/queries/ — 5-stage query model, KNN HNSW, RRF is Cloud rank(Rrf(...))
- https://cookbook.chromadb.dev/core/filters/ — where JSON schema
- https://cookbook.chromadb.dev/strategies/keyword-search/ — where_document $contains/$regex pattern
- https://github.com/xhluca/bm25s + .venv/Lib/site-packages/bm25s/tokenization.py — Lucene BM25, splitter (?u)\b\w\w+\b lower >=2 chars
- https://huggingface.co/intfloat/multilingual-e5-small — 384d, query:/passage: mandatory, CLS vs mean pooling
- https://sbert.net/docs/cross_encoder/usage/usage.html — CrossEncoder reranker vs bi-encoder, predict/rank
- https://sbert.net/docs/pretrained-models/ce-msmarco.html — MS MARCO table L6 1800 docs/sec NDCG 74.30
- https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2 — model card, training = MS MARCO passage ranking
- https://huggingface.co/BAAI/bge-reranker-v2-m3 — XLM-RoBERTa-large 568M multilingual, FlagReranker + normalize=True sigmoid
- https://github.com/FlagOpen/FlagEmbedding — BGE-M3 hybrid+rerank pipeline, bge-reranker-v2-m3 family table
- https://github.com/FlagOpen/FlagEmbedding/blob/master/research/BGE_M3/README.md — "We recommend hybrid retrieval + re-ranking"
- https://docs.cohere.com/docs/rerank + https://docs.cohere.com/reference/rerank — POST /v2/rerank relevance_score [0,1] normalized, not 2x interpretable
- https://docs.cohere.com/docs/reranking-best-practices / reranking-best-practices.mdx — threshold = mean borderline score over 30-50 queries
- https://github.com/qdrant/fastembed — TextCrossEncoder ONNX Runtime, no torch, rerank/rerank_pairs
- https://qdrant.tech/documentation/fastembed/fastembed-rerankers/ — TextCrossEncoder.list_supported_models() + rerank(query, docs) example
- https://qdrant.github.io/fastembed/examples/Supported_Models/ — 6 ONNX models table (Xenova L6 0.08GB ... Jina v2 1.11GB)
- https://github.com/qdrant/fastembed/blob/main/fastembed/rerank/cross_encoder/onnx_text_cross_encoder.py — supported_onnx_models, rerank -> logits, rerank_pairs(parallel)
- https://github.com/qdrant/fastembed/blob/main/fastembed/rerank/cross_encoder/text_cross_encoder.py — TextCrossEncoder dispatch + add_custom_model
- https://ai.pydantic.dev/agents/ + https://ai.pydantic.dev/tools-toolsets/tools/ — Agent.run_stream + tool docstring as description
- https://docs.trychroma.com general Chroma Cloud Search API rank(Rrf(...)) vs local manual RRF — https://chroma-core-chroma.mintlify.app/guides/hybrid-search pattern

**Prior research in this repo:**

- docs/research/bilingual-rag.md — E5 cross-lingual single index rationale
- docs/research/citation-persistence.md — ModelResponse.metadata sidecar, collection.get(ids=) hydrate
- docs/research/search-functionality-comparison.md — ScholarFlow vs this repo end-to-end (RRF k=60, 384 vs 1024, ranking weights, boilerplate)
- docs/research/streaming-llm-frontend.md — stream_text(delta=True) + 120 s SSE contract
