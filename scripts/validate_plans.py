"""Sanity-check the deterministic planner + executor against the public set.

This is the correctness oracle the LLM planner is measured against.
"""
import json, collections, sys
from occam.ingest.parse import load_events
from occam.store.local import EventGraph
from occam.agents.plan import rule_plan, execute, init_sport_vocab
from occam.eval.metrics import answer_matches, score_evidence

events, _ = load_events("data/corpus.jsonl")
g = EventGraph(events); init_sport_vocab(g)
qs = [json.loads(l) for l in open("data/eval_public.jsonl")]

agg = collections.defaultdict(lambda: {"n":0,"ok":0,"rec":0.0,"prec":0.0,"noplan":0,"insuff":0})
fails = []
for q in qs:
    a = agg[q["qtype"]]; a["n"] += 1
    plan = rule_plan(q["question"])
    if not plan:
        a["noplan"] += 1; fails.append((q["qid"], q["qtype"], "NO PLAN", q["question"][:80], "", q["answer"][0])); continue
    res = execute(plan, g)
    ok = answer_matches(res.answer, q["answer"])
    es = score_evidence(res.doc_ids, q["gold_doc_ids"])
    a["ok"] += ok; a["rec"] += es.recall; a["prec"] += es.precision
    if not res.sufficient: a["insuff"] += 1
    if not ok:
        fails.append((q["qid"], q["qtype"], res.problem or "WRONG", q["question"][:80], str(res.answer)[:40], q["answer"][0][:40]))

print(f"{'qtype':<14}{'n':>4}{'acc':>8}{'ev-rec':>9}{'ev-prec':>9}{'noplan':>8}{'insuf':>7}")
T = {"n":0,"ok":0,"rec":0.0,"prec":0.0,"noplan":0,"insuff":0}
for t, a in sorted(agg.items()):
    for k in T: T[k] += a[k]
    print(f"{t:<14}{a['n']:>4}{a['ok']/a['n']:>8.1%}{a['rec']/a['n']:>9.1%}{a['prec']/a['n']:>9.1%}{a['noplan']:>8}{a['insuff']:>7}")
print(f"{'TOTAL':<14}{T['n']:>4}{T['ok']/T['n']:>8.1%}{T['rec']/T['n']:>9.1%}{T['prec']/T['n']:>9.1%}{T['noplan']:>8}{T['insuff']:>7}")
print(f"\n=== {len(fails)} failures ===")
for f in fails: print(f"  [{f[0]}] {f[1]:<12} {f[2][:42]}\n      Q: {f[3]}\n      got={f[4]!r} want={f[5]!r}")
