"""Parity check: TigerGraph must return what the reference store returns.

`occam.store.local` is the reference implementation the benchmark ran on, and
the GSQL in `occam.store.tigergraph` is meant to be the same model executed in
the database. That claim is only worth making if it is tested, so this runs the
same queries through both and reports every disagreement.

    python scripts/verify_tigergraph.py            # sample of each query type
    python scripts/verify_tigergraph.py --full     # every public question

Exits non-zero if anything disagrees, so it can gate a submission.
"""
from __future__ import annotations

import argparse
import random
import sys

from dotenv import load_dotenv

from occam import context
from occam.agents.plan import Intent, execute, rule_plan
from occam.store import tigergraph as tg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="check all 100 public questions")
    ap.add_argument("--sample", type=int, default=6, help="questions per type otherwise")
    args = ap.parse_args()
    load_dotenv()

    ctx = context.load(with_index=False)
    local = ctx.graph
    conn = tg.connect()
    remote = tg.TigerGraphBackend(conn)

    print("  vertex counts in TigerGraph:")
    for name, n in remote.stats().items():
        print(f"    {name:<10} {n:>7,}")
    print(f"    (local reference holds {len(local.events):,} events)\n")

    qs = context.questions("eval_public.jsonl")
    if not args.full:
        by_type: dict[str, list] = {}
        for q in qs:
            by_type.setdefault(q["qtype"], []).append(q)
        random.seed(0)
        qs = [q for group in by_type.values()
              for q in random.sample(group, min(args.sample, len(group)))]

    checked = mismatched = skipped = 0
    for q in qs:
        plan = rule_plan(q["question"])
        if plan is None:
            skipped += 1
            continue
        want = execute(plan, local)

        try:
            if plan.intent is Intent.COUNT_ABOVE:
                got, ev, _ = remote.count_above(plan.sport, plan.games_year,
                                                plan.games_season, plan.threshold or 0)
                got_answer, got_docs = str(got), ev
            elif plan.intent is Intent.ARGMAX:
                title, ev = remote.argmax_competitors(plan.sport, plan.games_year,
                                                      plan.games_season)
                got_answer, got_docs = title, ev
            elif plan.intent is Intent.FIELD_OF_EVENT:
                row = remote.event_by_title(plan.title) or {}
                got_answer = row.get(plan.field_name)
                got_docs = [row["doc_id"]] if row.get("doc_id") else []
            elif plan.intent is Intent.VENUE_DATE:
                rows = remote.event_at_venue_date(plan.venue, plan.date)
                got_answer = rows[0].get("gold") if len(rows) == 1 else None
                got_docs = [r.get("doc_id") for r in rows]
            else:
                skipped += 1
                continue
        except Exception as exc:
            print(f"  ERROR  {q['qid']:<9} {plan.intent.value:<12} "
                  f"{type(exc).__name__}: {exc}")
            mismatched += 1
            continue

        checked += 1
        same_answer = str(got_answer) == str(want.answer)
        same_docs = set(got_docs or []) == set(want.doc_ids)
        if not (same_answer and same_docs):
            mismatched += 1
            print(f"  DIFF   {q['qid']:<9} {plan.intent.value}")
            if not same_answer:
                print(f"           answer   local={want.answer!r}  tigergraph={got_answer!r}")
            if not same_docs:
                only_l = set(want.doc_ids) - set(got_docs or [])
                only_r = set(got_docs or []) - set(want.doc_ids)
                print(f"           evidence local-only={sorted(only_l)[:4]} "
                      f"tigergraph-only={sorted(only_r)[:4]}")

    print(f"\n  checked {checked}, mismatched {mismatched}, "
          f"skipped {skipped} (no GSQL route yet)")
    if mismatched:
        print("  FAIL: TigerGraph and the reference store disagree")
        return 1
    print("  PASS: TigerGraph reproduces the reference results")
    return 0


if __name__ == "__main__":
    sys.exit(main())
