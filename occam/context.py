"""Shared construction of the graph, index and LLM handles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from occam.agents.plan import init_sport_vocab
from occam.ingest.parse import load_events
from occam.llm import LLM
from occam.store.local import EventGraph
from occam.store.vectors import HybridIndex

DATA = Path("data")


@dataclass
class Context:
    graph: EventGraph
    index: HybridIndex
    docs: list[dict]

    def llm(self) -> LLM:
        return LLM()


def load(with_index: bool = True, verbose: bool = True) -> Context:
    load_dotenv()
    docs = [json.loads(l) for l in open(DATA / "corpus.jsonl", encoding="utf-8") if l.strip()]
    events, others = load_events(DATA / "corpus.jsonl")
    g = EventGraph(events)
    init_sport_vocab(g)
    if verbose:
        print(f"  graph: {len(events)} events, {len(others)} non-event docs")
    index = HybridIndex.build(docs, verbose=verbose) if with_index else None
    return Context(graph=g, index=index, docs=docs)


def questions(name: str) -> list[dict]:
    return [json.loads(l) for l in open(DATA / name, encoding="utf-8") if l.strip()]
