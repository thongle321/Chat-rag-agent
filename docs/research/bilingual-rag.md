# Bilingual RAG Research — chat-rag-agent

Date: 2026-08-22
Scope: Make the RAG system handle Vietnamese + English queries against Vietnamese legal documents correctly, with answer language = query language and stable citations.

## Summary (no overengineering, modern, scalable)

**Choice: Keep a single mixed-language index, dense cross-lingual retrieval via `multilingual-e5-small`, and prompt-only bilingual behavior.** This is the minimal modern approach that scales — no per-language collections, no translation service, no custom stemmer. Verified against primary sources below.

---

## 1. Embedding Model — `intfloat/multilingual-e5-small`

* **Repo wiring — primary source:** `backend/app/core/config.py:21` `embedding_model: str = "intfloat/multilingual-e5-small"`; `backend/app/db/embeddings.py:14-48` registers custom `fastembed` model `pooling: CLS, dim: 384, model_file: onnx/model.onnx` and applies `query_prefix() -> "query: "` / `passage_prefix() -> "passage: "` (`embeddings.py:25`, used at `embeddings.py:123` and `rag.py:120`).
* **Model card — primary source:** `https://huggingface.co/intfloat/multilingual-e5-small/raw/main/config.json` → `{"hidden_size":384, "vocab_size":250037, "tokenizer_class":"XLMRobertaTokenizer", "max_position_embeddings":512}`; `sentence_bert_config.json` `max_seq_length:512`; `README.md` front-matter `language: vi, en, ... ~100` and body verbatim `Each input text should start with "query: " or "passage: ", even for non-English texts.` and `Yes, this is how the model is trained, otherwise you will see a performance degradation.` Prefix rules for asymmetric passage retrieval also on card.
* **Verdict:** Single shared vector space handles `query: What is traffic fine?` → `passage: Nghị định 135... phạt` without translation. Prefixes already correct in repo — **no change needed** for bilingual. `CLS` pooling override is a minor caveat (upstream notes mean-pooling for E5) but not bilingual-specific.

## 2. Vector Store — ChromaDB + BM25 Hybrid

* **Repo wiring — primary source:** `backend/app/db/vector_store.py:42-50` `_VI_STOPWORDS` (22 words) + `STOPWORDS_EN`; `vector_store.py:53 rrf(k=60)`; `vector_store.py:143 hybrid_query` does `bm25s.tokenize(query_text, stopwords=_STOPWORDS)` `k*2` each side + RRF + `get` by fused ids; `vector_store.py:65` `PersistentClient(.chromadb)` `hnsw:space cosine`.
* **BM25 tokenizer — primary source:** `.venv/Lib/site-packages/bm25s/tokenization.py` `lower=True, splitter=r"(?u)\b\w\w+\b"` (≥2 chars, `(?u)` unicode), `bm25s/stopwords.py` `STOPWORDS_EN` 34 words. Vietnamese not a built-in stopword set — repo's 22-word list is the only VI handling. `stemmer=None`.
* **Chroma hybrid pattern — primary source:** `https://chroma-core-chroma.mintlify.app/guides/hybrid-search` confirms no native BM25 — parallel BM25 + RRF is the prescribed pattern (repo does this).
* **Bilingual gap (acknowledged, not overengineered):** English query tokens never match Vietnamese BM25 vocab (`phạt`, `hành`). Dense must compensate. Equal RRF weighting mildly dilutes English queries. **Scalable fix is to leave it as-is** — dense cross-lingual is the modern answer; expanding stopwords / diacritic normalization / language-aware RRF weighting is deferred until measured pain (Regal context triad: RAG for content, prompt for behavior — dont bloat retrieval with heavy branching).

## 3. Prompt / Agent — pydantic-ai

* **Repo wiring — primary source:** `backend/app/core/config.py:22` `context_prompt` 8 rules (rule 1 catalog-in-context, rule 2 `search_documents`, rule 8 `Answer in the same language as the user's question`); `backend/app/services/rag.py:128-166` `search_documents` (docstring → `tool.description`), `list_documents`, `RunAgent` injects `Available documents in the library:\n- clean_title (Ref:) — chunks` into `system_prompt` every turn and recreates `Agent(..., system_prompt=system_prompt, tools=[search_documents, list_documents], capabilities=[ProcessHistory, ReinjectSystemPrompt])`.
* **Pydantic AI pattern — primary source:** `https://ai.pydantic.dev/agents/` + `https://ai.pydantic.dev/tools-toolsets/tools/` — `system_prompt`/`instructions` is the prompt mechanism, tool description = docstring, no built-in i18n. Established pattern is prompt instruction `Answer in {lang}`. Tool Choice `tool_choice` is ignored by Ollama per docs table — prompt + docstring is the lever.
* **Context-engineering principle — primary source:** Regal AI blog “Context Engineering: Prompt vs RAG vs Custom Action” (Mar 2026) — *prompt for always-loaded behavior + small stable facts (catalog), RAG for large/variable content*. Injecting titles (tens of lines) is lean; injecting full chunks is bloat. Repo follows the lean pattern.

## 4. Ingestion

* **Repo wiring — primary source:** `backend/app/services/document_ingest.py:36` `SUMMARY_PROMPT` Title/Reference, `Lit eParse vie+eng dpi 400`, `RecursiveChunker(chunk_size 1200)`, `base_metadata {title, clean_title, reference, type}` (no `language` field). `OCR_language vie+eng` already bilingual-capable.

---

## Decision (modern, no overengineering, scalable)

* **Keep single Chroma collection** — `multilingual-e5-small` cross-lingual dense is the modern approach; partitioning by language adds ops without benefit.
* **Keep hybrid as-is** — BM25 helps Vietnamese queries (exact legal terms, Refs like `135/2026/NĐ-CP`), dense handles English. No language detector, no RRF re-weighting now — measure first.
* **No `language` metadata yet** — add only when English docs arrive at scale. Deferred.
* **Bilingual behavior = prompt only:** rule 8 `Answer in the same language as the user's question` + catalog injection already makes the model automatically aware (no extra tool round). Tool `list_documents` remains as stale-refresh. Citations stay **verbatim** (original `clean_title` + `Ref`), not translated — legally safe and zero extra service.
* **Change in this PR:** One clarifying sentence added to rule 3 to make verbatim explicit; research note added. Nothing else.

## Verification

* `ruff check app/core/config.py app/services/rag.py`
* `tests/test_chat_stream.py` still passes (both tools in schema)
* Manual: `What documents do you have?` (en) → English wrapper + Vietnamese titles verbatim; `Bạn có những tài liệu gì?` (vi) → fully Vietnamese. English content query still retrieves Vietnamese decree via dense.

## Alternatives Considered and Rejected

* **Translate titles on the fly** — prompt could say “translate title to query language.” Rejected: legal-title hallucination risk, extra instruction bloat, not needed for `everything in there language` where proper nouns should stay original (common RAG provenance guidance).
* **Language-aware RRF / diacritic normalization / expanded stopwords** — real improvements, but overengineering before metric proves pain. Deferred.
* **Per-language collections + language filter** — scales poorly with mixed queries.

## Sources

* `https://huggingface.co/intfloat/multilingual-e5-small/raw/main/config.json`
* `https://huggingface.co/intfloat/multilingual-e5-small/raw/main/README.md`
* `https://huggingface.co/intfloat/multilingual-e5-small/raw/main/sentence_bert_config.json`
* `.venv/Lib/site-packages/fastembed/text/pooled_embedding.py` (E5 pooling note)
* `.venv/Lib/site-packages/bm25s/tokenization.py` + `bm25s/stopwords.py`
* `https://chroma-core-chroma.mintlify.app/guides/hybrid-search`
* `https://ai.pydantic.dev/agents/` + `https://ai.pydantic.dev/tools-toolsets/tools/`
* Regal AI: “Context Engineering for AI Agents: When to Use RAG vs. Prompt” (Mar 2026)
* Repo: `backend/app/core/config.py:21`, `backend/app/db/embeddings.py:14`, `backend/app/db/vector_store.py:42`, `backend/app/services/rag.py:109`, `backend/app/services/document_ingest.py:36`, `backend/app/services/llm.py:17`
