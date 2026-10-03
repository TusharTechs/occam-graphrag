"""Build docs/data.js: the real metrics and recorded traces the site replays.

Nothing here is invented. Every number and every step comes from
artifacts/results_public.jsonl and the paired questions file.
"""
import json
from collections import defaultdict

PICK = ["pub-001", "pub-055", "pub-040", "pub-004", "pub-005", "pub-009"]
ORDER = ["rag", "graphrag", "agentic", "occam"]
PUB = "artifacts/results_public.jsonl"

rows = [json.loads(l) for l in open(PUB)]
by = defaultdict(dict)
for r in rows:
    by[r["qid"]][r["pipeline"]] = r


def slim(r):
    return {
        "answer": r["answer"], "correct": r["correct"], "tokens": r["tokens"]["total"],
        "latency": r["latency_s"], "tier": r["tier"], "stop": r["stop_reason"],
        "recall": r["evidence_recall"], "docs": len(r["doc_ids"]),
        "steps": [{"agent": t["agent"], "action": t["action"], "detail": t["detail"],
                   "tokens": t["tokens"]["total"], "latency": t["latency_s"],
                   "outcome": t["outcome"]} for t in r["trace"]],
    }


gold = {}
for l in open("data/eval_public.jsonl"):
    g = json.loads(l)
    gold[g["qid"]] = g
questions = []
for q in PICK:
    d = by[q]
    questions.append({"qid": q, "question": d["rag"]["question"], "qtype": d["rag"]["qtype"],
                      "gold": gold[q]["answer"][0], "goldDocs": len(gold[q]["gold_doc_ids"]),
                      "runs": {p: slim(d[p]) for p in ORDER}})


def agg(p):
    rs = [by[q][p] for q in by]
    n = len(rs)
    c = sum(1 for r in rs if r["correct"])
    tok = sum(r["tokens"]["total"] for r in rs)
    return {"acc": c / n, "tokQ": tok / n, "tokCorrect": tok / max(c, 1),
            "recall": sum(r["evidence_recall"] for r in rs) / n}


bytype = defaultdict(lambda: defaultdict(list))
for q in by:
    for p in ORDER:
        bytype[by[q]["rag"]["qtype"]][p].append(1 if by[q][p]["correct"] else 0)
tiers = defaultdict(list)
for q in by:
    tiers[by[q]["occam"]["tier"]].append(by[q]["occam"]["tokens"]["total"])

data = {
    "n": len(by),
    "metrics": {p: agg(p) for p in ORDER},
    "byType": {t: {**{p: sum(v) / len(v) for p, v in d.items()}, "n": len(d["rag"])}
               for t, d in bytype.items()},
    "tiers": [{"tier": t, "n": len(v), "tokQ": sum(v) / len(v)} for t, v in tiers.items()],
    "questions": questions,
}
open("docs/data.js", "w").write("window.OCCAM_DATA = " + json.dumps(data, indent=1) + ";\n")
print("wrote docs/data.js", len(data["questions"]), "questions")
