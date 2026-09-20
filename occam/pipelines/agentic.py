"""Pipeline 3 - Agentic GraphRAG.

The orchestrator writes a plan, looks at what came back, and decides what to do
next.  It is allowed to rewrite the plan, to call a disambiguation agent when a
traversal returns several candidates, and to fall back to document retrieval
when the graph has no route to the answer.

The loop stops as soon as the evidence is sufficient.  Stopping early is the
behaviour being measured: extra steps are only worth taking when they change
the answer, so every iteration records why it happened.
"""

from __future__ import annotations

import time

from occam.agents.plan import Intent, PlanResult, execute
from occam.llm import LLM, extract_json
from occam.pipelines.base import PipelineResult, Step, timed
from occam.pipelines.graphrag import _ACTION_FOR, plan_step
from occam.store.local import EventGraph
from occam.store.vectors import HybridIndex

MAX_ITERATIONS = 3

_DISAMBIGUATE_SYSTEM = (
    "You resolve ambiguity between candidate Olympic events. "
    "Given a question and several candidate event titles, choose the one the "
    "question is actually about. Reply with JSON: "
    '{"choice": "<exact candidate title>", "why": "<short reason>"} '
    'or {"choice": null, "why": "..."} if none of them fit.')


def _disambiguate(question: str, candidates: list[str], llm: LLM,
                  problem: str) -> tuple[str | None, object]:
    """Pick between candidates the graph could not separate structurally.

    This is the step that earns the agent tier its token cost: the graph has
    narrowed the world to a handful of rows, and the only thing left to apply
    is the constraint stated in the question's wording.
    """
    listing = "\n".join(f"- {c}" for c in candidates)
    prompt = (f"QUESTION: {question}\n\nThe graph returned several candidates "
              f"({problem}):\n{listing}\n\nWhich one does the question mean?")
    resp = llm.complete(prompt, system=_DISAMBIGUATE_SYSTEM, max_output_tokens=200)
    try:
        choice = extract_json(resp.text).get("choice")
    except ValueError:
        choice = None
    return (str(choice) if choice else None), resp


def _answer_from_title(g: EventGraph, title: str, field: str) -> PlanResult:
    ev = g.event_by_title(title)
    if not ev:
        return PlanResult(None, sufficient=False, problem=f"no_event_titled: {title}")
    cell = g.field_of(ev, field)
    return PlanResult(str(cell.value) if cell.value else None, [cell],
                      sufficient=cell.value is not None,
                      problem="" if cell.value else f"field_missing: {field}")


def run(question: str, qid: str, g: EventGraph, llm: LLM,
        index: HybridIndex | None = None, use_rules: bool = False,
        max_iterations: int = MAX_ITERATIONS) -> PipelineResult:
    res = PipelineResult(pipeline="agentic", qid=qid, question=question, tier="agentic")
    t0 = time.time()
    feedback: str | None = None
    out: PlanResult | None = None
    plan = None

    for it in range(max_iterations):
        plan, pstep = plan_step(question, llm, g, use_rules=use_rules and it == 0,
                                feedback=feedback)
        pstep.agent = "orchestrator" if it else pstep.agent
        res.add(pstep)
        if plan is None:
            break

        ex = Step("graph", _ACTION_FOR.get(plan.intent.value, "graph_query"),
                  f"iteration {it + 1}: {plan.intent.value}")
        with timed(ex):
            out = execute(plan, g)
        ex.doc_ids = out.doc_ids
        ex.chunks = len(out.evidence)
        ex.outcome = "ok" if out.sufficient else ("ambiguous" if out.candidates else "insufficient")
        res.add(ex)

        if out.sufficient:
            res.stop_reason = (f"evidence sufficient after {it + 1} iteration(s)"
                               if it else "evidence sufficient on first plan")
            break

        # Ambiguity has a cheaper remedy than re-planning: the graph already
        # found the right neighbourhood, so only the choice is missing.
        if out.candidates:
            ds = Step("disambiguator", "llm_disambiguate",
                      f"{len(out.candidates)} candidates: {out.problem}")
            with timed(ds):
                choice, resp = _disambiguate(question, out.candidates, llm, out.problem)
            ds.usage = resp.usage
            if choice:
                picked = _answer_from_title(g, choice, plan.answer_field)
                ds.detail += f" -> chose {choice!r}"
                ds.doc_ids = picked.doc_ids
                ds.outcome = "ok" if picked.sufficient else "insufficient"
                res.add(ds)
                res.strategy_changes += 1
                if picked.sufficient:
                    out = picked
                    res.stop_reason = "resolved ambiguity with a constraint from the question"
                    break
            else:
                ds.outcome = "insufficient"
                res.add(ds)

        feedback = out.problem or "previous plan returned no usable evidence"
        res.strategy_changes += 1

    # Last resort: the graph has no route, so read documents instead.
    if (out is None or not out.sufficient) and index is not None:
        fb = Step("fallback_retriever", "vector_similarity_search",
                  "graph exhausted - falling back to document retrieval")
        with timed(fb):
            hits = index.search(question, k=8)
        fb.doc_ids = list(dict.fromkeys(c.doc_id for c, _ in hits))
        fb.chunks = len(hits)
        context = "\n\n".join(f"[{i+1}] {c.title} (doc {c.doc_id})\n{c.text}"
                              for i, (c, _) in enumerate(hits))
        r = llm.complete(
            f"EXCERPTS\n{context}\n\nQUESTION: {question}\n"
            "Answer with the exact value only, or INSUFFICIENT.",
            system="Answer only from the excerpts. Shortest exact value, or INSUFFICIENT.",
            max_output_tokens=200)
        fb.usage = r.usage
        ans = r.text.strip()
        ok = not ans.upper().startswith("INSUFFICIENT")
        fb.outcome = "ok" if ok else "insufficient"
        res.add(fb)
        res.strategy_changes += 1
        if ok:
            res.answer = ans
            res.citations = [f"{c.title} [{c.doc_id}]" for c, _ in hits]
            res.stop_reason = "answered from documents after graph found no route"
            res.latency_s = time.time() - t0
            return res

    if out is not None:
        res.answer = out.answer
        res.citations = [e.cite() for e in out.evidence]
        if out.incomplete_fields and plan is not None:
            res.notes.append(
                f"{len(out.incomplete_fields)} event(s) in scope lack "
                f"{plan.field_name}; count is over documented events only")
    if not res.stop_reason:
        res.stop_reason = (f"gave up after {max_iterations} iterations: "
                           f"{out.problem if out else 'no plan'}")
    res.latency_s = time.time() - t0
    return res
