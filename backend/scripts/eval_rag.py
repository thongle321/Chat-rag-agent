#!/usr/bin/env python3
"""Batch RAG evaluator — scores historical chat sessions for 4 quality metrics.

Metrics: Faithfulness, Answer Relevance, Context Precision, Context Recall.
Run from backend/ directory:
  python -m scripts.eval_rag [--limit N] [--output FILE] [--format json|markdown]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Add backend to path so app modules are importable
_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.models.session import ChatSession
from app.services.eval import EvalResult, OllamaJudge, evaluate_answer
from app.services.rag import get_messages, vector_store


async def get_all_sessions(db: AsyncSession, limit: int | None = None) -> list[ChatSession]:
    query = select(ChatSession).order_by(ChatSession.updated_at.desc())
    if limit:
        query = query.limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def evaluate_sessions(limit: int | None = None) -> list[dict]:
    """Score all (or last N) chat sessions. Returns list of scored results."""
    judge = OllamaJudge()
    retriever = vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 5},
    )
    results = []

    async with async_session_factory() as db:
        sessions = await get_all_sessions(db, limit)
        print(f"Found {len(sessions)} sessions to evaluate.\n")

        for i, session in enumerate(sessions, 1):
            messages = await get_messages(session.id)
            if len(messages) < 2:
                continue

            # Find first user question + corresponding assistant answer
            question = None
            answer = None
            for msg in messages:
                if msg["role"] == "user" and question is None:
                    question = msg["content"]
                elif msg["role"] == "assistant" and answer is None:
                    answer = msg["content"]
                if question and answer:
                    break

            if not question or not answer:
                continue

            print(f"[{i}/{len(sessions)}] {session.title[:50]}...")

            # Re-retrieve context for this question
            try:
                docs = retriever.invoke(question)
            except Exception as e:
                print(f"  Retrieval failed: {e}")
                docs = []

            # Score
            try:
                eval_result = evaluate_answer(question, answer, docs, judge)
            except Exception as e:
                print(f"  Scoring failed: {e}")
                eval_result = EvalResult(error=str(e))

            results.append({
                "session_id": session.id,
                "title": session.title,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "question": question[:200],
                "answer_preview": answer[:200],
                "num_sources": len(docs),
                "scores": eval_result.to_dict(),
            })
            print(f"  → overall={eval_result.overall:.2f}  faith={eval_result.faithfulness:.2f}  rel={eval_result.answer_relevance:.2f}  prec={eval_result.context_precision:.2f}  recall={eval_result.context_recall:.2f}")

    return results


def print_summary(results: list[dict]):
    if not results:
        print("\nNo results to summarize.")
        return

    valid = [r for r in results if r["scores"]["error"] is None]
    errored = [r for r in results if r["scores"]["error"] is not None]

    def avg(key):
        vals = [r["scores"][key] for r in valid]
        return sum(vals) / len(vals) if vals else 0.0

    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Total sessions:   {len(results)}")
    print(f"Scored:           {len(valid)}")
    print(f"Errors/skipped:   {len(errored)}")
    print()
    print(f"Avg faithfulness:       {avg('faithfulness'):.3f}")
    print(f"Avg answer relevance:   {avg('answer_relevance'):.3f}")
    print(f"Avg context precision:  {avg('context_precision'):.3f}")
    print(f"Avg context recall:     {avg('context_recall'):.3f}")
    print(f"Avg overall:            {avg('overall'):.3f}")
    print()

    # Worst 5
    if valid:
        worst = sorted(valid, key=lambda r: r["scores"]["overall"])[:5]
        print("Worst 5:")
        for r in worst:
            s = r["scores"]
            print(f"  {s['overall']:.2f}  {r['title'][:40]}")
    print()


def format_markdown(results: list[dict]) -> str:
    lines = ["# RAG Evaluation Report\n", f"Generated: {datetime.now().isoformat()}\n"]

    valid = [r for r in results if r["scores"]["error"] is None]

    def avg(key):
        vals = [r["scores"][key] for r in valid]
        return sum(vals) / len(vals) if vals else 0.0

    lines.append("## Summary\n")
    lines.append(f"| Metric | Score |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Sessions evaluated | {len(valid)} |")
    lines.append(f"| Avg faithfulness | {avg('faithfulness'):.3f} |")
    lines.append(f"| Avg answer relevance | {avg('answer_relevance'):.3f} |")
    lines.append(f"| Avg context precision | {avg('context_precision'):.3f} |")
    lines.append(f"| Avg context recall | {avg('context_recall'):.3f} |")
    lines.append(f"| Avg overall | {avg('overall'):.3f} |")
    lines.append("")

    lines.append("## Per-Session Results\n")
    lines.append("| Session | Overall | Faithfulness | Relevance | Precision | Recall |")
    lines.append("|---------|---------|--------------|-----------|-----------|--------|")
    for r in sorted(results, key=lambda x: x["scores"]["overall"]):
        s = r["scores"]
        err = f" ⚠ {s['error']}" if s["error"] else ""
        lines.append(
            f"| {r['title'][:40]} | {s['overall']:.2f}{err} | "
            f"{s['faithfulness']:.2f} | {s['answer_relevance']:.2f} | "
            f"{s['context_precision']:.2f} | {s['context_recall']:.2f} |"
        )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Batch RAG quality evaluator")
    parser.add_argument("--limit", type=int, default=None, help="Max sessions to evaluate")
    parser.add_argument("--output", type=str, default=None, help="Output file path")
    parser.add_argument("--format", choices=["json", "markdown"], default="json", help="Output format")
    args = parser.parse_args()

    results = asyncio.run(evaluate_sessions(limit=args.limit))
    print_summary(results)

    if args.output:
        out = Path(args.output)
        if args.format == "markdown":
            out.write_text(format_markdown(results), encoding="utf-8")
        else:
            out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Results written to {out}")
    elif args.format == "markdown":
        print(format_markdown(results))


if __name__ == "__main__":
    main()
