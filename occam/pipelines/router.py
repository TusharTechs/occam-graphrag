"""OCCAM - the cost-aware escalation controller.

The hackathon's stated research question is not "is agentic better" but
"are the extra reasoning and retrieval steps worth their token cost".  This
pipeline answers it operationally: start at the cheapest tier that could
possibly answer, and climb only when the evidence comes back insufficient.

    tier 0  rule-matched plan + graph query      ~0 LLM tokens
    tier 1  LLM-planned graph query              1 LLM call
    tier 2  agentic loop (re-plan, disambiguate) several calls
    tier 3  document fallback                    retrieval + read

Escalation is driven by the executor's own verdict, never by a guess about
difficulty: a tier hands over only when it can say *what* it was missing.
This matters because it means the controller cannot silently skip evidence -
every escalation is accompanied by the complaint that triggered it.
"""

from __future__ import annotations

import time

from occam.agents.plan import PlanResult, execute, rule_plan
from occam.llm import LLM
from occam.pipelines import agentic
from occam.pipelines.base import PipelineResult, Step, timed
from occam.pipelines.graphrag import _ACTION_FOR, plan_step
from occam.store.local import EventGraph
from occam.store.vectors import HybridIndex


def _resolve(question: str, out: PlanResult, answer_field: str, g: EventGraph,
             llm: LLM, res: PipelineResult) -> PlanResult | None:
    """Apply the question's own constraint to a shortlist the graph returned."""
    ds = Step("disambiguator", "llm_disambiguate",
              f"{len(out.candidates)} candidates: {out.problem}")
    with timed(ds):
        choice, resp = agentic._disambiguate(question, out.candidates, llm, out.problem)
    ds.usage = resp.usage
    picked = agentic._answer_from_title(g, choice, answer_field) if choice else None
    if picked is not None:
        ds.detail += f" -> chose {choice!r}"
        ds.doc_ids = picked.doc_ids
    ds.outcome = "ok" if (picked and picked.sufficient) else "insufficient"
    res.add(ds)
    return picked if (picked and picked.sufficient) else None


def run(question: str, qid: str, g: EventGraph, llm: LLM,
        index: HybridIndex | None = None) -> PipelineResult:
    res = PipelineResult(pipeline="occam", qid=qid, question=question)
    t0 = time.time()

    # -- tier 0: a plan we already know how to write ------------------------
    step = Step("router", "rule_match", "try deterministic plan cache")
    with timed(step):
        plan = rule_plan(question)
    step.outcome = "ok" if plan else "insufficient"
    step.detail = f"matched {plan.note}" if plan else "no rule matched"
    res.add(step)

    if plan is not None:
        ex = Step("graph", _ACTION_FOR.get(plan.intent.value, "graph_query"),
                  f"tier 0: {plan.intent.value}")
        with timed(ex):
            out = execute(plan, g)
        ex.doc_ids, ex.chunks = out.doc_ids, len(out.evidence)
        ex.outcome = "ok" if out.sufficient else ("ambiguous" if out.candidates else "insufficient")
        res.add(ex)
        if out.sufficient:
            res.tier = "tier0_rule_graph"
            res.answer = out.answer
            res.citations = [e.cite() for e in out.evidence]
            if out.incomplete_fields:
                res.notes.append(
                    f"{len(out.incomplete_fields)} event(s) in scope lack "
                    f"{plan.field_name}; count is over documented events only")
            res.stop_reason = "answered at tier 0 with no LLM call"
            res.latency_s = time.time() - t0
            return res
        res.notes.append(f"escalated from tier 0: {out.problem}")

        # Ambiguity is not a planning failure. The traversal already found the
        # right neighbourhood and returned a shortlist, so re-planning just
        # reproduces the same shortlist at full price - go straight to the
        # step that applies the constraint the question states.
        if out.candidates:
            resolved = _resolve(question, out, plan.answer_field, g, llm, res)
            if resolved is not None:
                res.tier = "tier1_disambiguated"
                res.answer = resolved.answer
                res.citations = [e.cite() for e in resolved.evidence]
                res.strategy_changes += 1
                res.stop_reason = ("resolved a tier 0 ambiguity without re-planning")
                res.latency_s = time.time() - t0
                return res

    # -- tier 1: let the model write the plan -------------------------------
    pstep, out1 = None, None
    plan1, pstep = plan_step(question, llm, g, use_rules=False)
    res.add(pstep)
    if plan1 is not None:
        ex = Step("graph", _ACTION_FOR.get(plan1.intent.value, "graph_query"),
                  f"tier 1: {plan1.intent.value}")
        with timed(ex):
            out1 = execute(plan1, g)
        ex.doc_ids, ex.chunks = out1.doc_ids, len(out1.evidence)
        ex.outcome = "ok" if out1.sufficient else ("ambiguous" if out1.candidates else "insufficient")
        res.add(ex)
        if out1.sufficient:
            res.tier = "tier1_llm_graph"
            res.answer = out1.answer
            res.citations = [e.cite() for e in out1.evidence]
            if out1.incomplete_fields:
                res.notes.append(
                    f"{len(out1.incomplete_fields)} event(s) in scope lack "
                    f"{plan1.field_name}; count is over documented events only")
            res.stop_reason = "answered at tier 1 with a single planning call"
            res.latency_s = time.time() - t0
            return res
        res.notes.append(f"escalated from tier 1: {out1.problem}")
        if out1.candidates:
            resolved = _resolve(question, out1, plan1.answer_field, g, llm, res)
            if resolved is not None:
                res.tier = "tier2_disambiguated"
                res.answer = resolved.answer
                res.citations = [e.cite() for e in resolved.evidence]
                res.strategy_changes += 1
                res.stop_reason = "resolved a tier 1 ambiguity without re-planning"
                res.latency_s = time.time() - t0
                return res

    # -- tier 2/3: hand over to the agent, carrying the cost already paid ----
    sub = agentic.run(question, qid, g, llm, index=index, use_rules=False)
    for s in sub.steps:
        res.add(s)
    res.answer = sub.answer
    res.citations = sub.citations
    res.notes.extend(sub.notes)
    res.strategy_changes = sub.strategy_changes + len(
        [n for n in res.notes if n.startswith("escalated")])
    res.tier = ("tier3_document_fallback"
                if any(s.agent == "fallback_retriever" for s in sub.steps)
                else "tier2_agentic")
    res.stop_reason = sub.stop_reason
    res.latency_s = time.time() - t0
    return res
