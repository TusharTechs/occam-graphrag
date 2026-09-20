"""Benchmark runner.

Runs the same questions through every pipeline and records answer accuracy,
evidence precision/recall against ``gold_doc_ids``, token cost and the full
agentic trace, so the comparison rests on one set of measurements rather than
four differently-instrumented runs.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from occam.eval.metrics import answer_matches, score_evidence
from occam.llm import LLM
from occam.pipelines import agentic, graphrag, rag, router
from occam.pipelines.base import PipelineResult
from occam.store.local import EventGraph
from occam.store.vectors import HybridIndex

PIPELINES = ("rag", "graphrag", "agentic", "occam")


@dataclass
class Scored:
    result: PipelineResult
    qtype: str
    correct: bool | None          # None when the question has no published answer
    ev_precision: float
    ev_recall: float
    ev_f1: float

    def to_json(self) -> dict:
        d = self.result.to_json()
        d.update(qtype=self.qtype, correct=self.correct,
                 evidence_precision=round(self.ev_precision, 4),
                 evidence_recall=round(self.ev_recall, 4),
                 evidence_f1=round(self.ev_f1, 4))
        return d


def run_one(pipeline: str, q: dict, g: EventGraph, index: HybridIndex,
            llm: LLM) -> PipelineResult:
    qid, question = q["qid"], q["question"]
    if pipeline == "rag":
        return rag.run(question, qid, index, llm)
    if pipeline == "graphrag":
        return graphrag.run(question, qid, g, llm, use_rules=False)
    if pipeline == "agentic":
        return agentic.run(question, qid, g, llm, index=index, use_rules=False)
    if pipeline == "occam":
        return router.run(question, qid, g, llm, index=index)
    raise ValueError(f"unknown pipeline: {pipeline}")


def score(result: PipelineResult, q: dict) -> Scored:
    gold = q.get("answer")
    correct = answer_matches(result.answer, gold) if gold else None
    es = score_evidence(result.doc_ids, q.get("gold_doc_ids", []))
    return Scored(result, q.get("qtype", "unknown"), correct,
                  es.precision, es.recall, es.f1)


class _Limiter:
    """Simple request-per-minute throttle shared across worker threads."""

    def __init__(self, rpm: int):
        self._min_gap = 60.0 / max(rpm, 1)
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.time()
            sleep_for = max(0.0, self._next - now)
            self._next = max(now, self._next) + self._min_gap
        if sleep_for:
            time.sleep(sleep_for)


def run_benchmark(questions: list[dict], g: EventGraph, index: HybridIndex,
                  llm_factory, pipelines: tuple[str, ...] = PIPELINES,
                  workers: int = 4, rpm: int = 240,
                  progress: bool = True) -> list[Scored]:
    """Execute every (question, pipeline) pair and score it.

    A fresh LLM handle per task keeps the per-result token totals independent;
    the shared limiter keeps the whole run inside the provider's rate limit.
    """
    limiter = _Limiter(rpm)
    tasks = [(p, q) for q in questions for p in pipelines]
    out: list[Scored] = []
    done = 0

    def work(pipeline: str, q: dict) -> Scored:
        limiter.wait()
        llm = llm_factory()
        try:
            r = run_one(pipeline, q, g, index, llm)
        except Exception as exc:                 # one bad question must not sink the run
            r = PipelineResult(pipeline=pipeline, qid=q["qid"], question=q["question"],
                               error=f"{type(exc).__name__}: {exc}",
                               stop_reason="pipeline raised")
        return score(r, q)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(work, p, q): (p, q) for p, q in tasks}
        for fut in as_completed(futures):
            out.append(fut.result())
            done += 1
            if progress and done % 20 == 0:
                print(f"    {done}/{len(tasks)} runs complete", flush=True)
    return out


def save(scored: list[Scored], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for s in sorted(scored, key=lambda x: (x.result.qid, x.result.pipeline)):
            fh.write(json.dumps(s.to_json(), ensure_ascii=False) + "\n")
    return path
