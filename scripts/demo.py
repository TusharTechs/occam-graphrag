"""Walk one question through all four pipelines, printing the full trace.

This is the script behind the demo video: pick a question, watch RAG guess,
watch GraphRAG stop at an ambiguity, watch the agent resolve it, and watch the
router reach the same answer for a fraction of the tokens.

    python scripts/demo.py pub-055
"""
import sys

from occam import context
from occam.eval.harness import run_one, score

BAR = "─" * 78


def main() -> None:
    qid = sys.argv[1] if len(sys.argv) > 1 else "pub-055"
    ctx = context.load()
    qs = {q["qid"]: q for q in context.questions("eval_public.jsonl")}
    if qid not in qs:
        qs |= {q["qid"]: q for q in context.questions("eval_hidden.jsonl")}
    q = qs[qid]

    print(f"\n{BAR}\nQUESTION [{qid}] ({q.get('qtype','?')})\n  {q['question']}")
    if q.get("answer"):
        print(f"  gold answer: {q['answer'][0]}")
        print(f"  gold evidence: {len(q.get('gold_doc_ids', []))} document(s)")
    print(BAR)

    for pipeline in ("rag", "graphrag", "agentic", "occam"):
        llm = ctx.llm()
        r = run_one(pipeline, q, ctx.graph, ctx.index, llm)
        s = score(r, q)
        verdict = {True: "CORRECT", False: "WRONG", None: "n/a"}[s.correct]
        print(f"\n### {pipeline.upper():<9} {verdict}   "
              f"{r.usage.total:,} tokens · {r.n_steps} steps · {r.latency_s:.1f}s"
              f"{' · tier ' + r.tier if r.tier else ''}")
        for i, st in enumerate(r.steps, 1):
            print(f"   {i}. {st.agent:<20} {st.action:<28} "
                  f"{st.usage.total:>5}t  [{st.outcome}]")
            if st.detail:
                print(f"      {st.detail[:96]}")
        print(f"   answer : {r.answer!r}")
        print(f"   stopped: {r.stop_reason}")
        print(f"   evidence: recall {s.ev_recall:.0%} precision {s.ev_precision:.0%} "
              f"({len(r.doc_ids)} docs)")
        for c in r.citations[:3]:
            print(f"      - {c[:92]}")
        if len(r.citations) > 3:
            print(f"      ... {len(r.citations)-3} more")
        for n in r.notes:
            print(f"   note: {n}")
    print(f"\n{BAR}")


if __name__ == "__main__":
    main()
