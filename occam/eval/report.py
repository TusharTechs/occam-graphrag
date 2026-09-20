"""Aggregate raw benchmark results into the metrics the guidebook asks for.

Everything here is computed from ``artifacts/results_*.jsonl``; nothing is
hand-entered, so the dashboard cannot drift from the run that produced it.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

PIPELINE_ORDER = ["rag", "graphrag", "agentic", "occam"]
QTYPE_ORDER = ["lookup", "multi_hop", "temporal", "aggregation", "superlative"]

PIPELINE_LABEL = {
    "rag": "RAG",
    "graphrag": "GraphRAG",
    "agentic": "Agentic GraphRAG",
    "occam": "OCCAM (routed)",
}


@dataclass
class Agg:
    n: int = 0
    correct: int = 0
    tokens: int = 0
    steps: int = 0
    latency: float = 0.0
    ev_p: float = 0.0
    ev_r: float = 0.0
    errors: int = 0
    strategy_changes: int = 0
    token_list: list[int] = field(default_factory=list)

    def add(self, row: dict) -> None:
        self.n += 1
        self.correct += 1 if row.get("correct") else 0
        tok = row["tokens"]["total"]
        self.tokens += tok
        self.token_list.append(tok)
        self.steps += row["n_steps"]
        self.latency += row["latency_s"]
        self.ev_p += row.get("evidence_precision", 0.0)
        self.ev_r += row.get("evidence_recall", 0.0)
        self.errors += 1 if row.get("error") else 0
        self.strategy_changes += row.get("strategy_changes", 0)

    @property
    def accuracy(self) -> float:
        return self.correct / self.n if self.n else 0.0

    @property
    def avg_tokens(self) -> float:
        return self.tokens / self.n if self.n else 0.0

    @property
    def median_tokens(self) -> float:
        return statistics.median(self.token_list) if self.token_list else 0.0

    @property
    def avg_steps(self) -> float:
        return self.steps / self.n if self.n else 0.0

    @property
    def avg_latency(self) -> float:
        return self.latency / self.n if self.n else 0.0

    @property
    def evidence_precision(self) -> float:
        return self.ev_p / self.n if self.n else 0.0

    @property
    def evidence_recall(self) -> float:
        return self.ev_r / self.n if self.n else 0.0

    @property
    def cost_to_correct(self) -> float:
        """Tokens spent per correct answer - the headline efficiency number.

        Undefined when nothing was answered correctly, reported as infinity so
        it sorts last rather than looking free.
        """
        return self.tokens / self.correct if self.correct else float("inf")


def load_rows(path: str | Path) -> list[dict]:
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def by_pipeline(rows: list[dict]) -> dict[str, Agg]:
    out: dict[str, Agg] = defaultdict(Agg)
    for r in rows:
        out[r["pipeline"]].add(r)
    return dict(out)


def by_pipeline_qtype(rows: list[dict]) -> dict[tuple[str, str], Agg]:
    out: dict[tuple[str, str], Agg] = defaultdict(Agg)
    for r in rows:
        out[(r["pipeline"], r.get("qtype", "unknown"))].add(r)
    return dict(out)


def tier_breakdown(rows: list[dict]) -> dict[str, dict]:
    """How often OCCAM settled at each tier, and what that cost."""
    out: dict[str, dict] = defaultdict(lambda: {"n": 0, "correct": 0, "tokens": 0})
    for r in rows:
        if r["pipeline"] != "occam":
            continue
        t = r.get("tier") or "unknown"
        out[t]["n"] += 1
        out[t]["correct"] += 1 if r.get("correct") else 0
        out[t]["tokens"] += r["tokens"]["total"]
    return dict(out)


def agent_value(rows: list[dict]) -> dict:
    """Where the agent tier actually changed the outcome.

    This is the hackathon's headline question made countable: compare the
    agentic run against the single-pass GraphRAG run on the same question and
    classify every disagreement.
    """
    g = {r["qid"]: r for r in rows if r["pipeline"] == "graphrag"}
    a = {r["qid"]: r for r in rows if r["pipeline"] == "agentic"}
    rescued, broke, both_ok, both_bad = [], [], 0, 0
    extra_tokens = 0
    for qid, ar in a.items():
        gr = g.get(qid)
        if not gr:
            continue
        gc, ac = bool(gr.get("correct")), bool(ar.get("correct"))
        extra_tokens += ar["tokens"]["total"] - gr["tokens"]["total"]
        if ac and not gc:
            rescued.append(qid)
        elif gc and not ac:
            broke.append(qid)
        elif gc and ac:
            both_ok += 1
        else:
            both_bad += 1
    n = len(a)
    return {
        "n": n,
        "rescued": rescued,
        "regressed": broke,
        "both_correct": both_ok,
        "both_wrong": both_bad,
        "extra_tokens_total": extra_tokens,
        "extra_tokens_per_rescue": (extra_tokens / len(rescued)) if rescued else float("inf"),
        "share_where_agent_mattered": (len(rescued) / n) if n else 0.0,
    }


def summary_text(rows: list[dict]) -> str:
    """Plain-text summary for the console and the README."""
    bp = by_pipeline(rows)
    bpq = by_pipeline_qtype(rows)
    lines: list[str] = []
    w = f"{'pipeline':<18}{'n':>4}{'acc':>8}{'complete':>10}{'ev-prec':>9}" \
        f"{'tok/q':>9}{'tok/correct':>13}{'steps':>7}{'s/q':>7}{'err':>5}"
    lines.append(w)
    lines.append("-" * len(w))
    for p in PIPELINE_ORDER:
        a = bp.get(p)
        if not a:
            continue
        ctc = "inf" if a.cost_to_correct == float("inf") else f"{a.cost_to_correct:,.0f}"
        lines.append(
            f"{PIPELINE_LABEL[p]:<18}{a.n:>4}{a.accuracy:>8.1%}{a.evidence_recall:>8.1%}"
            f"{a.evidence_precision:>9.1%}{a.avg_tokens:>9,.0f}{ctc:>13}"
            f"{a.avg_steps:>7.1f}{a.avg_latency:>7.1f}{a.errors:>5}")

    lines.append("")
    lines.append("accuracy by question type")
    head = f"{'qtype':<14}" + "".join(f"{PIPELINE_LABEL[p]:>19}" for p in PIPELINE_ORDER)
    lines.append(head)
    lines.append("-" * len(head))
    for qt in QTYPE_ORDER:
        row = f"{qt:<14}"
        for p in PIPELINE_ORDER:
            a = bpq.get((p, qt))
            row += f"{(f'{a.accuracy:.0%} ({a.avg_tokens:,.0f}t)' if a else '-'):>19}"
        lines.append(row)

    av = agent_value(rows)
    lines.append("")
    lines.append("where the agent tier mattered (agentic vs single-pass GraphRAG)")
    lines.append(f"  rescued   : {len(av['rescued'])}/{av['n']} questions "
                 f"({av['share_where_agent_mattered']:.0%})  {', '.join(av['rescued'][:8])}")
    lines.append(f"  regressed : {len(av['regressed'])}  {', '.join(av['regressed'][:8])}")
    lines.append(f"  extra cost: {av['extra_tokens_total']:,} tokens total")
    if av["rescued"]:
        lines.append(f"              {av['extra_tokens_per_rescue']:,.0f} tokens per question rescued")

    tiers = tier_breakdown(rows)
    if tiers:
        lines.append("")
        lines.append("OCCAM routing")
        for t, d in sorted(tiers.items(), key=lambda kv: -kv[1]["n"]):
            lines.append(f"  {t:<26} {d['n']:>3} questions  "
                         f"{d['correct'] / d['n']:>6.0%} correct  "
                         f"{d['tokens'] / d['n']:>8,.0f} tok/q")
    return "\n".join(lines)
