"""End-to-end RAG smoke check against the live index and a live Ollama.

Asks a set of in-scope and deliberately out-of-scope questions and reports
what actually came back: retrieval scores, whether the LLM was used, the
citations, and whether the out-of-scope questions were correctly refused.

    python scripts/verify_rag.py [--no-llm]
"""

import argparse
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.rag.pipeline import pipeline  # noqa: E402
from app.rag.prompt import FALLBACK_MESSAGE  # noqa: E402
from app.rag.vector_store import vector_store  # noqa: E402

IN_SCOPE = [
    ("What is the minimum attendance requirement?", "attendance"),
    ("When are the semester examinations held?", "examinations"),
    ("How do I get a bonafide certificate?", "certificates"),
    ("What subjects are taught in the third year of computer science?", "courses"),
    ("Which documents do I need at the time of admission?", "admissions"),
    ("What scholarships are available and what is the income limit?", "scholarships"),
    ("What is the eligibility criteria for campus placements?", "placements"),
    ("How much is the hostel fee and does it include food?", "hostel"),
    ("What happens if I pay my fees late?", "fees"),
    ("What are the library timings?", "general"),
]

OUT_OF_SCOPE = [
    "What is the capital of France?",
    "Who won the football world cup in 2018?",
    "Write me a Python function to sort a list.",
    "What is the stock price of Apple today?",
]

FOLLOW_UP = [
    "How much is the hostel fee?",
    "Does that include meals?",
]


def run(no_llm: bool) -> int:
    print("=" * 78)
    print("RAG VERIFICATION")
    print("=" * 78)
    print(f"Embedding model : {settings.EMBEDDING_MODEL}")
    print(f"LLM             : {settings.OLLAMA_MODEL} @ {settings.OLLAMA_BASE_URL}")
    print(f"top_k / thresh  : {settings.TOP_K} / {settings.SIMILARITY_THRESHOLD}")
    print(f"Indexed chunks  : {vector_store.count()}")

    llm_status = pipeline.llm.status()
    print(f"Ollama          : available={llm_status['available']} "
          f"model_pulled={llm_status.get('model_pulled')}")
    if llm_status.get("detail"):
        print(f"                  {llm_status['detail']}")

    if vector_store.count() == 0:
        print("\nNo chunks indexed. Run: python scripts/seed_demo.py")
        return 1

    if no_llm:
        class _Down:
            def generate(self, *_a, **_k):
                from app.rag.ollama_client import OllamaUnavailableError

                raise OllamaUnavailableError("Forced --no-llm mode.")

            def status(self):
                return {"available": False, "model": "n/a", "model_pulled": False}

        pipeline.llm = _Down()

    failures = 0

    print("\n" + "-" * 78)
    print("IN-SCOPE QUESTIONS (expected: grounded answer with citations)")
    print("-" * 78)
    for question, topic in IN_SCOPE:
        started = time.perf_counter()
        result = pipeline.answer(question)
        elapsed = time.perf_counter() - started

        ok = result.grounded and result.citations
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1

        print(f"\n[{status}] {question}   ({topic})")
        print(f"       similarity={result.top_similarity:.3f} llm_used={result.llm_used} "
              f"{elapsed:.1f}s")
        answer_preview = " ".join(result.answer.split())[:240]
        print(f"       answer: {answer_preview}")
        for citation in result.citations[:3]:
            print(f"       source: {citation.title} p{citation.page} "
                  f"(sim={citation.similarity:.3f})")

    print("\n" + "-" * 78)
    print("OUT-OF-SCOPE QUESTIONS (expected: refusal, no citations)")
    print("-" * 78)
    for question in OUT_OF_SCOPE:
        result = pipeline.answer(question)
        refused = (not result.grounded) or FALLBACK_MESSAGE[:40].lower() in result.answer.lower()
        status = "PASS" if refused else "FAIL"
        if not refused:
            failures += 1
        print(f"\n[{status}] {question}")
        print(f"       similarity={result.top_similarity:.3f} grounded={result.grounded}")
        print(f"       answer: {' '.join(result.answer.split())[:200]}")

    print("\n" + "-" * 78)
    print("MULTI-TURN FOLLOW-UP (expected: second answer stays on hostel fees)")
    print("-" * 78)
    history: list[dict] = []
    for question in FOLLOW_UP:
        result = pipeline.answer(question, history=history)
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": result.answer})
        titles = {c.title for c in result.citations}
        print(f"\n  Q: {question}")
        print(f"     similarity={result.top_similarity:.3f} sources={sorted(titles)}")
        print(f"     answer: {' '.join(result.answer.split())[:220]}")

    follow_up_ok = any("Hostel" in c.title for c in result.citations)
    if not follow_up_ok:
        failures += 1
        print("\n  [FAIL] follow-up lost the hostel context")
    else:
        print("\n  [PASS] follow-up retrieved hostel context from the previous turn")

    print("\n" + "=" * 78)
    print(f"RESULT: {'ALL CHECKS PASSED' if failures == 0 else f'{failures} CHECK(S) FAILED'}")
    print("=" * 78)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-llm", action="store_true", help="Simulate Ollama being down.")
    sys.exit(run(parser.parse_args().no_llm))
