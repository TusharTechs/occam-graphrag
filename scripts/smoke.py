"""Run a handful of representative questions through all four pipelines."""
import sys
from occam import context
from occam.eval.harness import run_benchmark

ctx = context.load()
qs = {q["qid"]: q for q in context.questions("eval_public.jsonl")}
# one of each type, plus the two the deterministic path cannot resolve alone
picks = ["pub-009", "pub-005", "pub-002", "pub-001", "pub-004", "pub-055", "pub-099"]
sample = [qs[p] for p in picks if p in qs]

scored = run_benchmark(sample, ctx.graph, ctx.index, ctx.llm, workers=4, progress=False)
by = {}
for s in scored:
    by.setdefault(s.result.qid, {})[s.result.pipeline] = s

print(f"\n{'qid':<10}{'type':<13}{'pipeline':<10}{'ok':<4}{'tok':>7}{'stp':>4}{'rec':>6}  tier / answer")
for qid in picks:
    if qid not in by: continue
    for p in ("rag", "graphrag", "agentic", "occam"):
        s = by[qid].get(p)
        if not s: continue
        r = s.result
        mark = "OK" if s.correct else ("--" if r.error else "X")
        print(f"{qid:<10}{s.qtype:<13}{p:<10}{mark:<4}{r.usage.total:>7}{r.n_steps:>4}"
              f"{s.ev_recall:>6.2f}  {r.tier or p} | {str(r.answer)[:38]!r}")
    print(f"{'':<10}{'':<13}want: {qs[qid]['answer'][0][:60]!r}")
    print()
