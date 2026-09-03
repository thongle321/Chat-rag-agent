# Search Functionality Comparison — chat-rag-agent vs learning-resource-app (ScholarFlow)

Date: 2026-08-24
Scope: End-to-end search comparison — read external reference app at D:\learning-resource-app\learning-resource-app and this repo D:\chat-rag-agent, trace vector store / embeddings / hybrid retrieval / RAG / API routes / frontend UI, compare architecture and propose adoptions. All claims cite primary source (official docs or repo file path + line).

## Summary

**chat-rag-agent is an agentic RAG chatbot — search is a tool the LLM invokes to answer with streamed citations. ScholarFlow is a document-library search engine — search IS the product (browse + filter + visual OCR).** Both are hybrid (dense + sparse) but differ in embedding model, store, fusion, chunking, filtering, and provenance.

| Dimension | chat-rag-agent | ScholarFlow (learning-resource-app) |
|---|---|---|
| Purpose | Answer question from private docs | Find documents for a need |
| Retrieval | BM25 (bm25s) + dense multilingual-e5-small 384d + RRF k=60 | Keyword substring + dense BGE-M3 1024d + weighted rank fusion |
| Vector DB | chromadb PersistentClient .chromadb, hnsw:space cosine, collection documents | sqlite-vec vec0 virtual table ChunkEmbeddingIndex, cosine, better-sqlite3 WAL |
| LLM loop | pydantic-ai Agent.run_stream with search_documents tool, ReinjectSystemPrompt | No RAG answer — results are cards linking to viewer; optional POST /api/search/curate LLM triage READ_FIRST/READ_LATER/SKIP |
| Streaming | SSE text/event-stream data/sources/done/error, delta streaming | No streaming (plain Response.json) |
| Citations | Inline [1][2] + UAccordion Sources, hydrated via ModelResponse.metadata | Result card Nguon: title sourceLabel, matchReasons chips, deep link ?chunk=&from=search#matched-chunk |

**Verdict:** ScholarFlow search is more sophisticated as a *retrieval engine* (structured filters, relevance gating, observables, visual OCR). chat-rag-agent is more sophisticated as an *answer engine* (agentic tool, streaming, provenance). Gap to close is filtered retrieval, relevance gating, and observability — not a new vector DB.

---
## 1. Files Inspected

### ScholarFlow (external) — primary source: on-disk repo at D:\learning-resource-app\learning-resource-app

- src/app/api/search/route.ts:1-74 — POST search route, zod schema, 30-result limit, chunksPerDocument cap, SearchLog write, status triad OK/NO_RELEVANT_RESULTS/EMPTY_LIBRARY
- src/lib/search/hybrid-search.ts:1-214 — searchByVector, searchByKeyword, hybridSearch, Promise.allSettled, retrievalMode hybrid/semantic/keyword
- src/lib/search/ranking.ts:1-291 — normalizeSearchText (NFD diacritic strip), STOP_WORDS 37 VI stripped + 14 EN, QUERY_CONCEPT_ALIASES 17 vi-en mappings, inferSearchCriteria, rankSearchCandidatesWithDiagnostics (weighted 0.68/0.14/0.13/0.05/0.04 vs 0.82 semantic-only, SEMANTIC_ONLY_THRESHOLD 0.55, relevanceFloor max(0.32,bestScore-0.25), boilerplatePenalty 0.32)
- src/lib/vector/sqlite-vector-store.ts:1-256 — EMBEDDING_DIMENSIONS 1024, toSqliteVectorBlob/fromSqliteVectorBlob, cosineSimilarity, SqliteVectorStore (better-sqlite3 WAL, foreign_keys ON, platform-aware vec0.dll/.so/.dylib load), vec0(chunk_id TEXT PRIMARY KEY, embedding FLOAT[1024] distance_metric=cosine), searchChunkEmbeddings MATCH ? AND k=? 1-distance semanticScore, batch 30k ids
- src/lib/embedding/client.ts:1-142 — embedTexts via fetch EMBEDDING_SERVICE_URL/embed (health poll missing/loading/ready/error, 30s connect / 60min model deadline, 503 retry, 10-min embed timeout, 1024-dim validation)
- src/lib/embedding/config.ts:1-21 — batch 16 default / 32 max
- src/lib/embedding/embed-document.ts:1-89 — embedDocumentChunks batch flow, dual write ChunkEmbeddingIndex + DocumentChunk.embedding Blob, progress 0-100, AnalysisJob lifecycle
- mbedding-runtime/service.mjs:1-258 — Node http service :8001, BAAI/bge-m3 via @huggingface/transformers pipeline feature-extraction pooling cls normalize true, fp32 cpu onnxruntime-node, mock mode, DIMENSIONS 1024, health/modelRequiredFiles check
- src/lib/documents/chunk-text.ts:1-65 — word-window chunker TARGET 320 MAX 380 MIN_FINAL 180 OVERLAP 40 ratio 1.3 tok/word, chunkDocumentSections with pageNumber/sourceLabel
- src/lib/documents/extract-text.ts:1-294 — docling.rs hierarchical chunker + tesseract/vietnamese-ocr embedded-image OCR, MIN_EXTRACTED_TEXT_LENGTH 20, scan vs native routing, page provenance
- src/lib/documents/ocr-region.ts:1-76 — recognizeSearchRegion OCR tail queue, generation guard, MIN_OCR_TEXT_LENGTH 2, confidence <25 reject, route reject/formula
- src/lib/search/visual-query.ts:1-9 — mergeRecognizedText
- src/lib/search/visual-search-draft.ts:1-48 — in-memory VisualSearchDraft 15-min TTL (not persisted)
- src/lib/search/visual-image-crop.ts + isual-grid-cleanup.ts — crop map + removeLongGridLines
- src/components/search/semantic-search.tsx:1-338 — ResourceSearch text UI (debounce 500 ms, abort dedup, sessionStorage scholarflow:resource-search:v3, topic/difficulty/fileType filters, buildSuitabilityReasons)
- src/components/search/visual-resource-search.tsx:1-869 — VisualResourceSearch (upload MAX 40 MiB, canvas zoom 1-2x, pointer capture select/move/resize, captureOriginalImageRegion JPEG 0.95 + grid cleanup, dual OCR nativeText+capturedPreview, auto re-search 400 ms, AbortController 30/90 s)
- src/app/api/search/visual/ocr/route.ts:1-25 + isual/preview/route.ts:1-86 + curate/route.ts:1-114 — OCR, doc preview renderDocumentPreview, curate LLM classifier READ_FIRST/READ_LATER/SKIP
- prisma/schema.prisma:1-174 — Document, DocumentChunk {content, tokenCount, pageNumber, sourceLabel, embedding Bytes}, SearchLog, AnalysisJob, Tag/DocumentTag
- package.json:60-75 — deps sqlite-vec 0.1.9, better-sqlite3 13.0.2, docling.rs 0.53.3, next 16, zod 4.4
- mbedding-runtime/package.json:1-14 — @huggingface/transformers 4.2.0 + onnxruntime-node

### chat-rag-agent (this repo) — primary source: on-disk repo at D:\chat-rag-agent

- ackend/app/services/rag.py:1-368 — Deps/RAGState, _format_context [n] title (Ref) p.page, _track_sources dedup title+reference, search_documents(ctx, query) -> str (query_embedding via fastembed query: prefix -> hybrid_query k=8, no threshold), _catalog, RunAgent (Agent system_prompt catalog+context_prompt, tools=[search_documents], capabilities=[ProcessHistory(_keep_recent 10), ReinjectSystemPrompt]), stream_answer (agent.run_stream delta=True, re.findall citations, ModelResponse.metadata stubs before save_messages, event sources/done/error), get_messages hydration via get_vector_store().get_metadata
- ackend/app/db/vector_store.py:1-229 — VectorStore Protocol, _VI_STOPWORDS 22 + STOPWORDS_EN 34 =56, rrf(k=60) 1/(k+rank+1), ChromaVectorStore (PersistentClient .chromadb, hnsw:space cosine, collection documents, bm25_index persist bm25_ids.json, bm25s.BM25 lucene k1 1.2 b 0.75 tokenize stopwords, hybrid_query k*2 each side + RRF, get_metadata, list_documents, delete_document where title)
- ackend/app/db/embeddings.py:1-49 — _CUSTOM_MODELS multilingual-e5-small pooling CLS dim 384 onnx/model.onnx, query_prefix/passage_prefix, get_embeddings -> TextEmbedding
- ackend/app/services/document_ingest.py:1-164 — LiteParse cheap vs OCR vie+eng dpi400 via is_complex, RecursiveChunker character 1200 min 24, SUMMARY_PROMPT Title/Reference via Agent, base_metadata {title, clean_title, source, type, reference}, passage: prefix, BATCH 500
- ackend/app/api/chat.py:1-73 — POST /query + POST /query/stream SSE event_stream data/sources/done/error, StreamingResponse text/event-stream
- ackend/app/api/sessions.py:1-35 — GET /sessions/{id} -> SessionDetail via get_messages, DELETE
- ackend/app/models/schemas.py:1-55 — ChatRequest 1-2000, SessionSource {n,title,reference,pages}, SessionMessage {role,content,sources?}
- ackend/app/core/config.py:1-51 — embedding_model intfloat/multilingual-e5-small, context_prompt 8 rules (rule 8 answer in query language), vector_store_dir .chromadb
- ackend/pyproject.toml:1-59 — fastapi>=0.139, chromadb>=1.5<2, pydantic-ai>=2.19, chonkie>=0.1.0, fastembed>=0.5, bm25s>=0.3.10, liteparse conditional
- rontend/src/api/index.ts:1-95 — streamChat fetch POST /chat/query/stream -> ReadableStream getReader TextDecoder split newline currentEvent dispatch
- rontend/src/stores/chat.ts:1-263 — Pinia CHAT, localStorage chat_sessions, activeControllers Map per-conv, fetchSessionMessages hydrates sources, streaming true->false id swap
- rontend/src/pages/index.vue:1-216 — Comark streaming markdown stripInlineCitations, UAccordion Sources, per-source id citation-{msg.id}-{n} + activeCite, USkeleton single bubble, copy + Alert

---
## 2. Architecture End-to-End

### ScholarFlow (resource library)
```
Upload (pdf/pptx/docx/epub <=40 MiB)
 -> docling.rs convertFileAsync -> JSON -> parse Document -> chunkDocumentAsync hierarchical
   + embedded-image OCR (vietnamese-ocr 25-conf, formula routing) + scannedPdfSections
   -> sections {text, pageNumber, sourceLabel}
   -> chunk-text word-window (320 +-40) or hierarchical -> DocumentChunk rows
   -> embedDocumentChunks batch 16 -> POST 127.0.0.1:8001/embed (BGE-M3 CLS 1024) -> vec0 ChunkEmbeddingIndex + Blob
Search text:
 POST /api/search {query 2-500, chunksPerDocument 1-5, topic/difficulty/fileType/documentId/dateFrom/dateTo}
  -> Promise.allSettled(searchByVector + searchByKeyword) limit 30
    - vector: embedTexts -> vec0 MATCH k=30 ORDER BY distance -> semanticScore=1-distance
    - keyword: extractKeywordTerms -> normalizeSearchText padded includes title*2+content*1 + phrase 3/1.5 sort slice
  -> rankSearchCandidatesWithDiagnostics merge by chunkId weighted sum + coverage + bonuses - boilerplate
       pass = (lexicalCoverage>=0.5 if <=2 groups else 0.4 OR sem>=0.55) && filters
       sort vector-backed first then score desc -> filter accepted -> floor max(0.32,best-0.25) -> slice 30
  -> filter chunksPerDocument <=1 per doc -> slice 30 -> SearchLog
  -> return {query,status, interpretedQuery, retrievalMode, results}
  -> ResourceSearch cards -> Link /documents/[id]?chunk=&from=search#matched-chunk
Search visual:
 file upload -> preview (image blobUrl/pdf iframe/docx srcDoc HTML)
 -> drag selection -> captureOriginalImageRegion JPEG0.95 OR desktop capture -> extractNativeText + OCR -> textarea
 -> debounce 400 ms runSearch -> same hybrid pipeline
Curate: POST /api/search/curate {query, results 1-12} -> JSON {summary, items[READ_FIRST|READ_LATER|SKIP]}
```

### chat-rag-agent (conversational RAG)
```
Ingest:
 save_and_queue_indexing -> data/uploads/{filename} -> status pending
 -> LiteParse is_complex -> cheap vs OCR vie+eng 400dpi -> text
 -> _summarize(text[:3000]) via Agent -> Title/Reference
 -> base_metadata {title, clean_title, source, type, reference}
 -> RecursiveChunker(character 1200 min24) -> chunks
 -> embed [passage: + chunk] (fastembed 384d, batch 500) -> Chroma add uuid
Search agentic tool:
 POST /api/chat/query/stream {question 1-2000, session_id?}
  -> load_messages history 10 -> catalog -> system_prompt = context_prompt + catalog
  -> Agent tools=[search_documents] -> run_stream -> may call search_documents(query)
       search_documents: query_prefix+query -> embed -> hybrid_query k=8
           _ensure_bm25 ids -> k*2 each side -> rrf k=60 -> fused[:8] -> collection.get
       -> _track_sources dedup -> n pages -> _format_context [n] title p.N content
  -> stream_text delta=True -> text_delta -> done with stubs metadata -> save_messages -> sources/done
 Frontend: fetch ReadableStream dispatch onDelta Comark onSources accordion onDone id swap
 Reload: GET /sessions/{id} -> get_messages hydrate via get_metadata
```

---
## 3. Deep Comparison

| Axis | chat-rag-agent | ScholarFlow | Source refs |
|---|---|---|---|
| Goal | Answer with provenance | Discover relevant source | see 2 |
| Embedding | multilingual-e5-small 384d CLS normalized, prefixes query:/passage: mandatory else degrade, max 512 tokens, 94 langs incl vi | BGE-M3 1024d CLS normalized, prefix-less, 8192 tokens, multilingual | backend/app/db/embeddings.py:14-27, https://huggingface.co/intfloat/multilingual-e5-small, embedding-runtime/service.mjs:174, https://huggingface.co/BAAI/bge-m3 |
| Store | Chroma PersistentClient .chromadb HNSW cosine single collection | sqlite vec0 cosine better-sqlite3 WAL file storage/scholarflow.db manual vec0.dll/so Extension per arch offline/Electron | backend/app/db/vector_store.py:68-72 https://docs.trychroma.com/docs/collections/configure src/lib/vector/sqlite-vector-store.ts:142-146 https://github.com/asg017/sqlite-vec |
| Sparse | bm25s 0.3.10 Lucene k1 1.2 b 0.75 tokenize stopwords 56 splitter unicode >=2 chars lower no stemming vocab persisted bm25_ids.json | No BM25 lib — in-memory extractKeywordTerms + normalizeSearchText NFD strip diacritics df->d padded includes title x2 content x1 phrase 3/1.5 | backend/app/db/vector_store.py:98-106 .venv/bm25s/tokenization.py src/lib/search/ranking.ts:79-110 src/lib/search/hybrid-search.ts:150-180 |
| Fusion | RRF k=60 sum 1/(60+rank+1) equal-weighted 2 lists k*2 -> [:k] no normalization | Weighted sum 0.68 sem+0.14 kw+0.13 vecRank+0.05 kwRank+0.04 / 0.82 sem+0.18 vecRank else 0.62 kw+0.18 kwRank then 0.78 retrieval+0.12 contentCov+0.06 titleCov+0.04 topicCov+bonuses - boilerplate relevanceGate+floor max(0.32,best-0.25) | backend/app/db/vector_store.py:55-64 src/lib/search/ranking.ts:180-209 |
| Relevance control | None — model judges content if not docs return No relevant | SEMANTIC_ONLY_THRESHOLD 0.55 lexicalCoverage >=0.5 (<=2 groups) else 0.4 OR sem>=0.55 && filters satisfy relevanceFloor max(0.32,bestScore-0.25) boilerplatePenalty 0.32 | backend/app/services/rag.py:184 src/lib/search/ranking.ts:77-211 |
| Filters | None (all docs in catalog) Deletion by title only | topic difficulty fileType documentId dateFrom/dateTo Prisma where on both vector and keyword pre-filter + post-rank gates limit 30 chunksPerDocument dedup | src/lib/search/ranking.ts:112-132 src/lib/search/hybrid-search.ts:38-60 src/app/api/search/route.ts:29-35 |
| Chunking | RecursiveChunker character 1200 min 24 single boundary page not preserved chunk index as page proxy summary via LLM | chunkDocumentText word window 320/380 + overlap 40 minFinal 180 and chunkDocumentAsync hierarchical via docling preserves pageNumber/sourceLabel tokenCount | backend/app/services/document_ingest.py:29-33 https://github.com/chonkie-ai/chonkie src/lib/documents/chunk-text.ts:9-36 src/lib/documents/extract-text.ts:266 |
| Metadata | {title filename clean_title source type reference chunk summary} no language no pageNumber | {title originalFileName filePath fileType language primaryTopic difficulty summary analysisReason pageNumber sourceLabel tokenCount} rich taxonomy + tags | backend/app/services/document_ingest.py:83-89 prisma/schema.prisma:52-75 |
| Ingestion | Lightweight liteparse parse -> summarize -> chunk -> embed 4 states pending/processing/completed/failed no job table | Heavyweight docling.rs rust + tesseract OCR + vietnamese-ocr + embedded-image scan + visual routing 4 AnalysisJob types EXTRACT_TEXT/CHUNK_DOCUMENT/EMBED_DOCUMENT/ANALYZE_DOCUMENT PENDING-PROCESSING-COMPLETED-FAILED | backend/app/services/document_ingest.py:64-117 src/lib/documents/extract-text.ts:239-293 prisma/schema.prisma:32-44 |
| Observability | logger.info Catalog injected n no search log | SearchLog {query filters retrievalMode bestScore acceptanceThreshold rejectionReason resultDocumentIds} + AnalysisJob per step + diagnostics returned | backend/app/services/rag.py:215 prisma/schema.prisma:166-174 src/lib/search/ranking.ts:29-34 |
| Frontend UX | No dedicated search page — chat composer only streaming answer + source accordion Id cards reactive Pinia sources via backend | Text tab + Visual tab image/pdf/docx upload canvas viewer 1-2x zoom select/move/resize handles page nav captured preview OCR textarea editable examples pills filters empty-state sessionStorage persist in-memory 15-min draft | frontend/src/pages/index.vue:129-154 src/components/search/semantic-search.tsx:222-335 visual-resource-search.tsx:767-868 |
| Citation lifecycle | deps.retrieved -> _track_sources -> cited filter re findall -> state.sources -> ModelResponse.metadata sidecar in TEXT blob -> get_messages hydrate via get_metadata deleted drop rename surface single-message sources | Result cards are citation no message history pageNumber/sourceLabel per chunk citation Nguon title sourceLabel link preserves chunkId highlight | backend/app/services/rag.py:27-44,69-107,328-342 docs/research/citation-persistence.md src/components/search/semantic-search.tsx:326-328 |

---
## 4. Primary-Source Verification

Each claim is grounded in file content (line numbers) or library official docs/source, not secondary blogs:

- multilingual-e5-small prefixes + 384d + 512 tokens + vi+100 langs — model card https://huggingface.co/intfloat/multilingual-e5-small (README Each input must start with query: or passage: / Yes otherwise degradation; config.json hidden_size 384 vocab 250037 max_position_embeddings 512; sentence_bert_config max_seq 512) — verified in docs/research/bilingual-rag.md:15.
- BGE-M3 1024d — https://huggingface.co/BAAI/bge-m3 (card 1024 dims FlagEmbedding multi-granularity 8192 context) + local runtime embedding-runtime/service.mjs:15 DIMENSIONS 1024 and pooling cls normalize true.
- fastembed custom model override — https://github.com/qdrant/fastembed + site-package fastembed/text/... plus repo backend/app/db/embeddings.py:14-22 add_custom_model pooling CLS dim 384 onnx/model.onnx.
- Chroma persistent + HNSW cosine + no-native BM25 -> hybrid via parallel RRF — https://docs.trychroma.com/docs/collections/configure (hnsw:space) and https://chroma-core-chroma.mintlify.app/guides/hybrid-search (parallel BM25+RRF) implemented at backend/app/db/vector_store.py:69-74,145-174.
- bm25s tokenization + stopwords + Lucene — https://github.com/xhluca/bm25s and local .venv/Lib/site-packages/bm25s/tokenization.py (splitter (?u)\b\w\w+\b lower) + stopwords.py STOPWORDS_EN at backend/app/db/vector_store.py:10,52,98-103.
- sqlite-vec vec0 virtual table + cosine + MATCH ? AND k=? — https://github.com/asg017/sqlite-vec (CREATE VIRTUAL TABLE USING vec0 distance_metric=cosine WHERE embedding MATCH ? AND k=? ORDER BY distance) mirrored at src/lib/vector/sqlite-vector-store.ts:142-216 database.loadExtension vec0.dll/so/dylib per-arch.
- better-sqlite3 WAL + busy_timeout — https://github.com/WiseLibs/better-sqlite3 pragma journal_mode WAL at sqlite-vector-store.ts:133-135.
- chonkie RecursiveChunker — https://github.com/chonkie-ai/chonkie Recursive chunker character tokenizer 1200 at backend/app/services/document_ingest.py:29-33.
- liteparse OCR vie+eng dpi400 + is_complex — https://pypi.org/project/liteparse docs at document_ingest.py:25-27,69.
- pydantic-ai Agent.run_stream stream_text(delta) + ProcessHistory/ReinjectSystemPrompt + ModelResponse.metadata sidecar persisted via ModelMessagesTypeAdapter — https://ai.pydantic.dev/agents/ + /tools-toolsets/tools/ + /core-concepts/message-history/#storing-and-loading-messages-to-json (metadata not sent to LLM What survives round-trip) wired at backend/app/services/rag.py:204-232,309-340.
- FastAPI StreamingResponse SSE — https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse spec text/event-stream event: + data: + blank line at backend/app/api/chat.py:60-73 + frontend/src/api/index.ts:52-92.
- docling.rs convertFileAsync + chunkDocumentAsync hierarchical + checkDependencies — https://github.com/docling-project/docling oxide + npm docling.rs at src/lib/documents/extract-text.ts:1-12,250-266.
- tesseract.js / vietnamese-ocr confidence route — https://github.com/naptha/tesseract.js + src/lib/documents/ocr-region.ts:8-76 confidence <25 MIN_OCR_TEXT_LENGTH tail queue.
- Next.js App Router + Prisma — https://nextjs.org/docs/app/api-reference/file-conventions/route and https://prisma.io/docs at src/app/api/search/route.ts:18-74 and prisma/schema.prisma.
- SEARCH infrastructure — https://html.spec.whatwg.org/multipage/webstorage.html sessionStorage quota Zod https://zod.dev schema all verified.

---
## 5. What to Adopt (and What to Skip)

### Adopt — small diff, high value (ponytail minimal)

1. **Relevance gate + floor + diagnostics** — ScholarFlow passesRelevanceGate / relevanceFloor / bestScore prevents empty-answer hallucinations when retrieval is weak. chat-rag-agent trusts whatever hybrid_query k=8 returns. Add light gate on dense side (cosine via collection.query distances rescaled) or keyword-coverage heuristic after fusion, surface rejectedCandidateCount as diagnostics on event: sources. Cost ~20 lines in vector_store.py + rag; log bestScore per query.

2. **Lexical coverage + boilerplate penalty** — ScholarFlow groupCoverage (N bunches of alias groups) and hasBoilerplate (copyright/isbn/preface/table of contents at chunk start) is cheap (regex sets) and prunes PDF-front-matter spam. Add normalizeSearchText helper (NFD strip) and BOILERPLATE_PATTERNS constant subtract 0.3 from score. Prevents [1] citing title page.

3. **Structured filters (at least fileType / documentId / topic)** — ScholarFlow documentFilter via Prisma where is one-line way to let users ask search only in Decree 44/2025. Parallel in Chroma is where: {type: fileType} or where: {reference: ...}. Change search_documents(query, filters?) docstring + hybrid_query(..., where_filter?) Chroma where support already available on query/get. Pydantic AI docstring is contract — no schema bloat.

4. **SearchLog / metrics table** — ScholarFlow persists query,filters, retrievalMode,bestScore,acceptedThreshold,rejectionReason,resultDocumentIds. chat-rag-agent has no query log. Add tiny search_logs SQLite table or at minimum logger.info structured JSON with same fields helps tune stopwords/RRF/post-filter.

5. **chunksPerDocument dedup + result limit** — ScholarFlow chunksByDocument Map -> slice avoids one long doc dominating 8 slots. chat-rag-agent dedups by title+reference into numbered sources but can still emit 8 chunks from same file as 8 citations. Post-fusion filter per-doc <=2 chunks improves citation diversity. One-line guard in _track_sources/stream_answer.

6. **interpretedQuery feedback** — ScholarFlow returns inferSearchCriteria (difficulty/fileType/keywordGroups). Echoing interpreted filters in event: sources payload {sources, interpreted: {...}} makes agentic failures transparent.

### Consider — worth it only if use-case demands

7. **Word-window overlap chunking with pageNumber** — If legal citations need p. N precision migrate from chunk index to real page metadata. ScholarFlow preserves pageNumber/sourceLabel from Docling provenance. chat-rag-agent ponytail chunk stands in for page until real page metadata at ingest comment acknowledges gap. Requires liteparse returning page_no per page result it already yields pages with needs_ocr -> loop per page rather than flat text.

8. **Query normalization + alias groups** — ScholarFlow 17 Vietnamese-English aliases (khoang trong nghien cuu -> research gap mo hinh cay -> tree cau truc du lieu -> data structure) plus NFD diacritic stripping. Overkill for legal English-Vietnamese cross-lingual dense already handles translation keep stopwords expansion as only alias-like win. Add normalizeSearchText to BM25 path for diacritic tolerance only if users type ASCII nghien cuu.

9. **Visual search mode** — ScholarFlow canvas-crop -> OCR -> re-search loop is impressive for scanned exam sheets. chat-rag-agent could reuse as search_by_image(imageDataUrl) tool: client crops/uploads image -> server runs OCR (liteparse already has vie+eng) -> hybrid_query with recognized text. Tradeoff needs image upload endpoint + tesseract runtime in docker. Propose optional /api/documents/upload-image-query no-Electron keep desktop capture Electron-only.

10. **LLM curate (READ_FIRST/LATER/SKIP)** — Post-retrieval re-rank cost 1 LLM call useful when k=8 is noisy. For chat-rag-agent answering LLM itself is re-ranker (cites only cited IDs). Skip unless separate search-browse page is built.

### Skip — over-engineering for this repo

- **Migrate vector DB to sqlite-vec/better-sqlite3.** Chroma is correct server-side store (multi-client HNSW tunable python-native). sqlite-vec earns keep in Electron single-user offline switching adds platform-specific vec0 binary loading manual blob management and loses collection.query distance metadata without benefit.
- **Embed via sidecar HTTP service (BGE-M3 1024).** fastembed in-process ONNX 384d <150 MB RAM is lighter than ScholarFlow dedicated 127.0.0.1:8001 sidecar + onnxruntime-node + 1 GiB BGE-M3 download. Upsizing to 1024 doubles store + latency. Switch only if evaluated recall on Vietnamese legal corpus shows multilingual-e5-small underperforms measure first.
- **Heavy docling pipeline (rust + tesseract per embedded image).** ScholarFlow processes pptx/docx/epub + per-image Vietnamese formula OCR. chat-rag-agent ingests pdf/txt/md/csv/json/xml + images via liteparse sufficient for legal PDFs. Keep chonkie do not port docling.rs.
- **Per-job AnalysisJob table + progress bars.** ScholarFlow needs it for large library uploads chat-rag-agent single document_status + logfire is enough for admin view.
- **Topic/difficulty taxonomy auto-tagging.** ScholarFlow constrained classification + canonical tags is for learning resources legal RAG catalog is authority-driven title/reference.

---
## 6. Concrete Minimal Diffs (if adopting 5.1-5)

```python
# backend/app/db/vector_store.py — add normalize + boilerplate, no new dep
import unicodedata
_BOILERPLATE = {"copyright","all rights reserved","table of contents","preface"}
def _norm(t: str):  # ponytail: NFD strip is stdlib, no new lib
    return unicodedata.normalize("NFD", t).replace("đ","d").lower()
def _is_boilerplate(doc: str, meta: dict) -> bool:
    head = _norm(doc[:240]); label = _norm(meta.get("sourceLabel","") or "")
    return any(p in head or p in label for p in _BOILERPLATE)
# ranking gate after fused = rrf(...)[:k] keep only non-boilerplate or strong semantic log rejectionReason
```

```python
# backend/app/services/rag.py — per-doc cap (ponytail: one guard where all callers route)
def _track_sources(...):
    # existing dedup then if per_title_counts[title] >= 2: skip extras -> next best fused id
```

```python
# backend/app/api/chat.py — include diagnostics
# sources event becomes {"sources": [...], "diagnostics":{"k":8,"fused":len(fused),"boilerplateDropped":...}}
```

No new tables. Log line `logger.info("search query=%r fused=%d sources=%d mode=hybrid", query, len(fused), len(state.sources))` is SearchLog equivalent until table justified.

---

## 7. Open Questions for Team

- Do we need page-accurate p. N citations? If yes promote pageNumber otherwise chunk N is acceptable and cheaper.
- Confirm embedding upgrade path: benchmark multilingual-e5-small 384 vs bge-m3 1024 on 50 Vietnamese legal queries before changing model or sidecar.
- Is visual OCR in-scope for chat? If lawyers upload photo of a clause search_by_image may matter more than fileType filter.

---

## Sources — primary only

- Repo: backend/app/services/rag.py:1, rag.py:170, rag.py:328, rag.py:69, rag.py:204, backend/app/db/vector_store.py:42, vector_store.py:55, vector_store.py:68, vector_store.py:98, vector_store.py:145, backend/app/db/embeddings.py:14, backend/app/services/document_ingest.py:25, document_ingest.py:83, backend/app/core/config.py:21, backend/app/api/chat.py:55, backend/app/api/sessions.py:14, backend/app/models/schemas.py:34, frontend/src/api/index.ts:30, frontend/src/stores/chat.ts:112, frontend/src/pages/index.vue:129
- External: src/app/api/search/route.ts:7, src/lib/search/hybrid-search.ts:1, src/lib/search/ranking.ts:36, ranking.ts:79, ranking.ts:160, src/lib/vector/sqlite-vector-store.ts:6, sqlite-vector-store.ts:142, src/lib/embedding/client.ts:113, src/lib/embedding/embed-document.ts:17, embedding-runtime/service.mjs:8, service.mjs:134, src/lib/documents/chunk-text.ts:9, src/lib/documents/extract-text.ts:162, src/lib/documents/ocr-region.ts:47, src/components/search/semantic-search.tsx:46, src/components/search/visual-resource-search.tsx:50, src/lib/search/visual-query.ts:1, prisma/schema.prisma:52, prisma/schema.prisma:166, package.json:60
- Docs: https://huggingface.co/intfloat/multilingual-e5-small (config + sentence_bert_config + README prefixes), https://huggingface.co/BAAI/bge-m3 (1024 CLS), https://docs.trychroma.com/docs/collections/configure (hnsw:space), https://chroma-core-chroma.mintlify.app/guides/hybrid-search (parallel BM25+RRF), https://github.com/xhluca/bm25s + .venv/.../bm25s/tokenization.py, https://github.com/asg017/sqlite-vec (vec0), https://github.com/WiseLibs/better-sqlite3 (WAL), https://github.com/chonkie-ai/chonkie (RecursiveChunker), https://github.com/qdrant/fastembed (TextEmbedding), https://ai.pydantic.dev/agents/ + /tools-toolsets/tools/ + /core-concepts/message-history/#storing-and-loading-messages-to-json, https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse (StreamingResponse SSE), https://nextjs.org/docs/app/api-reference/file-conventions/route (Route Handlers), https://prisma.io/docs (schema), https://github.com/docling-project/docling (docling.rs), https://html.spec.whatwg.org/multipage/webstorage.html (sessionStorage), https://zod.dev (schema)
- Prior research in this repo: docs/research/bilingual-rag.md, docs/research/citation-persistence.md:1, docs/research/streaming-llm-frontend.md:1
