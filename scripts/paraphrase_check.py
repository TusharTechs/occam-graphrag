"""Generalisation check: questions deliberately worded off-template.

Tier 0's rule cache matches the five shapes in the supplied benchmark. The
obvious objection is that the system is tuned to those shapes, so this asks the
same facts in wordings no rule matches, and reports which tier answered. The
point is not the accuracy number alone -- it is that unmatched questions fall
through to the LLM planner rather than failing.
"""
from occam import context
from occam.agents.plan import rule_plan
from occam.eval.harness import run_one, score

CASES = [
    # (paraphrase, expected answer, what the benchmark would have asked)
    ("Across the whole corpus, tally the biathlon events at the 2018 Winter Games "
     "where the competitor count exceeded 73.", "5", "aggregation"),
    ("Which single sailing contest at the Sydney 2000 Olympics drew the largest "
     "field of athletes?", "Sailing at the 2000 Summer Olympics – Soling", "superlative"),
    ("Name the athlete who took first place in the men's 20 km racewalk at "
     "whichever Summer Games came directly before Rio 2016.", "Chen Ding", "temporal"),
    ("At the 2012 London Games, the Royal Artillery Barracks hosted an event on "
     "28 July 2012, so who claimed gold there?", "Yi Siling", "multi_hop"),
    ("How many different countries entered the women's 57 kg judo competition "
     "at Rio 2016?", "23", "lookup"),
    ("For the 2016 Olympic men's horizontal bar gymnastics final, what was the "
     "number of nations taking part?", "34", "lookup"),
]

ctx = context.load()
print(f"{'wording':<12}{'rule?':<8}{'tier':<26}{'tok':>6}  result")
print("-" * 78)
ok = 0
for text, expected, kind in CASES:
    matched = "yes" if rule_plan(text) else "NO"
    q = {"qid": f"para-{kind}", "question": text, "answer": [expected], "qtype": kind}
    r = run_one("occam", q, ctx.graph, ctx.index, ctx.llm())
    s = score(r, q)
    ok += bool(s.correct)
    print(f"{kind:<12}{matched:<8}{r.tier:<26}{r.usage.total:>6}  "
          f"{'CORRECT' if s.correct else 'WRONG'}  {str(r.answer)[:40]!r}")
print("-" * 78)
print(f"{ok}/{len(CASES)} correct on off-template wordings")
