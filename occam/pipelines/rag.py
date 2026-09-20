"""Pipeline 1 - vanilla RAG.

Similarity search over document chunks, then one LLM call to read them.  No
graph, no planning, no second look.  The point of keeping it strong (hybrid
retrieval, infobox-aware chunking) is that its failures should be *structural*
rather than the result of a weak baseline: on an aggregation question whose
answer spans 43 documents, no value of k inside a sane context budget can
contain the evidence.
"""

from __future__ import annotations

import time

from occam.eval.metrics import TokenUsage
from occam.llm import LLM
from occam.pipelines.base import PipelineResult, Step, timed
from occam.store.vectors import HybridIndex

_SYSTEM = ("You answer questions using only the provided document excerpts. "
           "Reply with the exact value and nothing else: a bare number for counts, "
           "the person's name exactly as written for medallists, and for 'which "
           "event' questions the COMPLETE page title of the event, in the form "
           "'Sport at the YEAR Season Olympics - Discipline'. "
           "If the excerpts do not contain the answer, reply exactly: INSUFFICIENT")

_PROMPT = """EXCERPTS
{context}

QUESTION: {question}

Answer with the exact value only. For "which event" questions give the full page title."""


def run(question: str, qid: str, index: HybridIndex, llm: LLM,
        k: int = 10) -> PipelineResult:
    res = PipelineResult(pipeline="rag", qid=qid, question=question, tier="rag")
    t0 = time.time()

    step = Step("retriever", "vector_similarity_search", f"top-{k} hybrid (dense+bm25)")
    with timed(step):
        hits = index.search(question, k=k)
    step.doc_ids = list(dict.fromkeys(c.doc_id for c, _ in hits))
    step.chunks = len(hits)
    step.outcome = "ok" if hits else "insufficient"
    res.add(step)

    context = "\n\n".join(
        f"[{i+1}] {c.title} (doc {c.doc_id})\n{c.text}" for i, (c, _) in enumerate(hits))

    read = Step("reader", "llm_read", f"{len(hits)} chunks in context")
    with timed(read):
        r = llm.complete(_PROMPT.format(context=context, question=question),
                         system=_SYSTEM, max_output_tokens=200)
    read.usage = r.usage
    ans = r.text.strip()
    read.outcome = "insufficient" if ans.upper().startswith("INSUFFICIENT") else "ok"
    res.add(read)

    res.answer = None if read.outcome == "insufficient" else ans
    res.citations = [f"{c.title} [{c.doc_id}]" for c, _ in hits]
    res.stop_reason = ("model reported insufficient evidence"
                       if read.outcome == "insufficient" else "single retrieval pass complete")
    res.latency_s = time.time() - t0
    return res
