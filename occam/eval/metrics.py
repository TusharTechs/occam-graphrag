"""Scoring for the three-way benchmark.

Answer accuracy alone cannot distinguish a system that found the right evidence
from one that guessed a plausible string.  The public question set ships
``gold_doc_ids``, so OCCAM scores retrieval directly: did the pipeline actually
put the required documents in front of the model?
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from occam.ingest.parse import norm_text


def answer_matches(predicted: str | None, gold: list[str]) -> bool:
    """Normalised exact match against any accepted gold answer.

    Numeric answers are compared as numbers so ``5`` and ``5.0`` agree; text is
    compared after unicode/dash normalisation so ``Men's marathon`` matches
    across the corpus's several dash characters.
    """
    if predicted is None:
        return False
    p = norm_text(str(predicted))
    for g in gold:
        gg = norm_text(str(g))
        if p == gg:
            return True
        try:
            if abs(float(p) - float(gg)) < 1e-9:
                return True
        except ValueError:
            pass
    return False


@dataclass
class EvidenceScore:
    precision: float
    recall: float
    f1: float
    retrieved: int
    gold: int
    hits: int


def score_evidence(retrieved_doc_ids: list[str], gold_doc_ids: list[str]) -> EvidenceScore:
    """Set precision/recall of retrieved documents against the gold set.

    Aggregation questions legitimately require reading every event in a sport,
    so low precision is not automatically a fault - it is reported alongside
    recall rather than folded into a single number.
    """
    r, g = set(retrieved_doc_ids), set(gold_doc_ids)
    hits = len(r & g)
    p = hits / len(r) if r else 0.0
    rec = hits / len(g) if g else 0.0
    f1 = (2 * p * rec / (p + rec)) if (p + rec) else 0.0
    return EvidenceScore(p, rec, f1, len(r), len(g), hits)


@dataclass
class TokenUsage:
    """Token accounting, split the way the guidebook asks for it."""
    context: int = 0
    llm_input: int = 0
    llm_output: int = 0

    @property
    def total(self) -> int:
        return self.llm_input + self.llm_output

    def add(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(self.context + other.context,
                          self.llm_input + other.llm_input,
                          self.llm_output + other.llm_output)

    def to_json(self) -> dict:
        d = asdict(self)
        d["total"] = self.total
        return d
