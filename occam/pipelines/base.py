"""Common result and trace types for all three pipelines.

The guidebook asks for a specific set of trace facts - which retrieval methods
were chosen, which agents ran, tokens and time per operation, whether the
system changed strategy, and when and why it stopped.  Recording those in one
shared structure is what lets the dashboard compare pipelines honestly instead
of comparing three differently-instrumented systems.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from occam.eval.metrics import TokenUsage


@dataclass
class Step:
    """One operation in an investigation."""
    agent: str                      # which specialised agent ran
    action: str                     # the tool/retrieval method it used
    detail: str = ""
    usage: TokenUsage = field(default_factory=TokenUsage)
    latency_s: float = 0.0
    doc_ids: list[str] = field(default_factory=list)
    chunks: int = 0
    outcome: str = ""               # ok | insufficient | ambiguous | error

    def to_json(self) -> dict:
        return {"agent": self.agent, "action": self.action, "detail": self.detail,
                "tokens": self.usage.to_json(), "latency_s": round(self.latency_s, 3),
                "doc_ids": self.doc_ids, "chunks": self.chunks, "outcome": self.outcome}


@dataclass
class PipelineResult:
    pipeline: str
    qid: str
    question: str
    answer: str | None = None
    citations: list[str] = field(default_factory=list)
    doc_ids: list[str] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    latency_s: float = 0.0
    tier: str = ""                  # which escalation tier produced the answer
    stop_reason: str = ""
    strategy_changes: int = 0       # times the plan was rewritten after evidence
    error: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def n_steps(self) -> int:
        return len(self.steps)

    @property
    def retrieval_methods(self) -> list[str]:
        seen, out = set(), []
        for s in self.steps:
            if s.action not in seen:
                seen.add(s.action)
                out.append(s.action)
        return out

    def add(self, step: Step) -> Step:
        self.steps.append(step)
        self.usage = self.usage.add(step.usage)
        for d in step.doc_ids:
            if d not in self.doc_ids:
                self.doc_ids.append(d)
        return step

    def to_json(self) -> dict:
        return {
            "pipeline": self.pipeline, "qid": self.qid, "question": self.question,
            "answer": self.answer, "citations": self.citations, "doc_ids": self.doc_ids,
            "tokens": self.usage.to_json(), "latency_s": round(self.latency_s, 3),
            "tier": self.tier, "stop_reason": self.stop_reason,
            "strategy_changes": self.strategy_changes,
            "n_steps": self.n_steps, "retrieval_methods": self.retrieval_methods,
            "n_citations": len(self.citations),
            "error": self.error, "notes": self.notes,
            "trace": [s.to_json() for s in self.steps],
        }


class timed:
    """Context manager recording wall time onto a Step."""

    def __init__(self, step: Step):
        self.step = step

    def __enter__(self) -> Step:
        self._t0 = time.time()
        return self.step

    def __exit__(self, *exc) -> None:
        self.step.latency_s = time.time() - self._t0
