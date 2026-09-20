"""Pipeline 2 - GraphRAG.

One planning call turns the question into a structured traversal, the graph
executes it, and the answer comes back with the documents it was read from.
There is no second look: if the plan comes back insufficient or ambiguous,
this pipeline reports that rather than investigating further.  That ceiling is
precisely what the agentic tier is measured against.
"""

from __future__ import annotations

import time

from occam.agents.plan import QueryPlan, execute, rule_plan
from occam.agents.planner import plan_with_llm
from occam.llm import LLM
from occam.pipelines.base import PipelineResult, Step, timed
from occam.store.local import EventGraph

_ACTION_FOR = {
    "field_of_event": "graph_vertex_lookup",
    "count_above": "graph_aggregation",
    "argmax": "graph_aggregation",
    "venue_date": "graph_traversal_venue_date",
    "prev_edition": "graph_traversal_prev_edition",
    "freeform": "none",
}


def plan_step(question: str, llm: LLM, g: EventGraph, *, use_rules: bool,
              feedback: str | None = None) -> tuple[QueryPlan | None, Step]:
    """Produce a plan, preferring the rule cache when it is allowed to.

    Returning the Step alongside the plan keeps token attribution honest: a
    rule-matched plan genuinely costs zero LLM tokens and the trace says so.
    """
    if use_rules and not feedback:
        step = Step("planner", "rule_match", "deterministic plan cache")
        with timed(step):
            plan = rule_plan(question)
        if plan:
            step.detail = f"matched {plan.note}"
            step.outcome = "ok"
            return plan, step
        step.detail = "no rule matched - escalating to LLM planner"
        step.outcome = "insufficient"

    step = Step("planner", "llm_plan", "question -> QueryPlan over graph schema")
    with timed(step):
        sports = sorted({e.sport for e in g.events if e.sport})
        plan, resp = plan_with_llm(question, llm, sports, feedback=feedback)
    step.usage = resp.usage
    step.detail = f"intent={plan.intent.value}" + (f" (after: {feedback})" if feedback else "")
    step.outcome = "ok"
    return plan, step


def run(question: str, qid: str, g: EventGraph, llm: LLM,
        use_rules: bool = False) -> PipelineResult:
    res = PipelineResult(pipeline="graphrag", qid=qid, question=question, tier="graphrag")
    t0 = time.time()

    plan, pstep = plan_step(question, llm, g, use_rules=use_rules)
    res.add(pstep)
    if plan is None:
        res.stop_reason = "no plan could be produced"
        res.latency_s = time.time() - t0
        return res

    ex = Step("graph", _ACTION_FOR.get(plan.intent.value, "graph_query"),
              f"plan={plan.to_json()}")
    with timed(ex):
        out = execute(plan, g)
    ex.doc_ids = out.doc_ids
    ex.chunks = len(out.evidence)
    ex.outcome = "ok" if out.sufficient else ("ambiguous" if out.candidates else "insufficient")
    res.add(ex)

    res.answer = out.answer
    res.citations = [e.cite() for e in out.evidence]
    if out.incomplete_fields:
        res.notes.append(
            f"{len(out.incomplete_fields)} event(s) in scope lack {plan.field_name}; "
            "count is over documented events only")
    res.stop_reason = ("single graph query satisfied the question" if out.sufficient
                       else f"stopped without escalating: {out.problem}")
    res.latency_s = time.time() - t0
    return res
