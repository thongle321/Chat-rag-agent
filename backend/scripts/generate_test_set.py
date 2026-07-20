#!/usr/bin/env python3
"""Generate a test set from indexed ChromaDB documents.

Usage from backend/ directory:
  python -m scripts.generate_test_set [--max N] [--output FILE]

Reads chunks from ChromaDB, uses the LLM to generate QA pairs,
and saves to data/test_set.json for use with eval_rag.py --test-set.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from app.services.rag import _get_model
from app.db.vector_store import chroma_collection

MAX_TEST_CASES = 20
SAMPLE_EVERY = 8  # sample every N chunks to get diverse questions


def load_chunks_from_chromadb() -> list[dict]:
    """Pull all chunks with metadata from ChromaDB."""
    result = chroma_collection.get(include=["metadatas", "documents"])
    if not result["ids"]:
        return []
    chunks = []
    for doc_id, meta, doc in zip(result["ids"], result["metadatas"], result["documents"]):
        chunks.append({
            "id": doc_id,
            "text": doc,
            "source": meta.get("title", "unknown"),
            "page": meta.get("page"),
        })
    return chunks


def generate_qa_from_chunk(chunk_text: str, source: str, llm) -> dict | None:
    """Use the LLM to generate a (query, ground_truth) pair from a chunk."""
    prompt = (
        "Given the following text excerpt, generate ONE factual question "
        "that can be answered from the text. Then provide the concise answer.\n"
        'Return ONLY a JSON object with keys "query" and "ground_truth". Nothing else.\n\n'
        f"Text: {chunk_text[:800]}\n\nJSON:"
    )
    try:
        response = llm.invoke([("human", prompt)])
        raw = response.content if hasattr(response, "content") else str(response)
        raw = re.sub(r"```(?:json)?\s*", "", raw)
        raw = re.sub(r"```\s*", "", raw).strip()
        match = re.search(r"\{.*?\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            query = data.get("query", "").strip()
            ground_truth = data.get("ground_truth", "").strip()
            if query and ground_truth:
                return {
                    "query": query,
                    "ground_truth": ground_truth,
                    "expected_sources": [source],
                }
    except Exception as e:
        print(f"  [WARN] QA generation failed: {e}")
    return None


def main():
    parser = argparse.ArgumentParser(description="Generate test set from ChromaDB")
    parser.add_argument("--max", type=int, default=MAX_TEST_CASES, help="Max test cases")
    parser.add_argument("--output", type=str, default=None, help="Output file path")
    args = parser.parse_args()

    print("=" * 60)
    print("GENERATE TEST SET")
    print("=" * 60)

    # Load chunks
    print("\n[1/3] Loading chunks from ChromaDB...")
    chunks = load_chunks_from_chromadb()
    if not chunks:
        print("  No chunks found. Upload and index documents first.")
        sys.exit(1)
    print(f"  Found {len(chunks)} chunks")

    # Sample diverse chunks
    step = max(1, len(chunks) // 8)
    sample_chunks = chunks[::step][:8]
    print(f"  Sampling {len(sample_chunks)} chunks for QA generation")

    # Generate test cases
    print("\n[2/3] Generating QA pairs with LLM...")
    llm = _get_model()
    test_cases = []

    for i, chunk in enumerate(sample_chunks):
        if len(test_cases) >= args.max:
            break
        print(f"  [{i+1}/{len(sample_chunks)}] {chunk['source'][:40]}...")
        qa = generate_qa_from_chunk(chunk["text"], chunk["source"], llm)
        if qa:
            test_cases.append(qa)
            print(f"    -> {qa['query'][:60]}...")
        time.sleep(0.2)

    if not test_cases:
        print("  No test cases generated.")
        sys.exit(1)

    # Save
    print(f"\n[3/3] Saving test set...")
    out_path = Path(args.output) if args.output else (_BACKEND / "data" / "test_set.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(test_cases, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'=' * 60}")
    print(f"DONE: {len(test_cases)} test cases saved to {out_path}")
    print(f"Run with: python -m scripts.eval_rag --test-set")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
