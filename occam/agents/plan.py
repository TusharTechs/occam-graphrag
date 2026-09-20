"""Query plans: the contract between reasoning and retrieval.

Every pipeline in OCCAM ultimately answers by executing a ``QueryPlan`` against
the graph.  What differs between pipelines is *who writes the plan* - a rule
matcher, one LLM call, or an agent that writes a plan, inspects the result and
rewrites it.  Keeping execution identical across all three is what makes the
three-way benchmark a fair comparison rather than three unrelated systems.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from occam.ingest.parse import norm_text
from occam.store.local import Evidence, EventGraph


class Intent(str, Enum):
    FIELD_OF_EVENT = "field_of_event"    # named event -> one infobox field
    COUNT_ABOVE = "count_above"          # sport+games, count field > threshold
    ARGMAX = "argmax"                    # sport+games, event maximising field
    VENUE_DATE = "venue_date"            # venue+date -> event -> medallist
    PREV_EDITION = "prev_edition"        # same series one Games earlier
    FREEFORM = "freeform"                # no structured route; fall back to text


@dataclass
class QueryPlan:
    intent: Intent
    title: str | None = None
    sport: str | None = None
    games_year: int | None = None
    games_season: str | None = None
    gender: str | None = None
    discipline: str | None = None
    venue: str | None = None
    date: str | None = None
    field_name: str = "competitors"
    threshold: int | None = None
    answer_field: str = "gold"
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        d = {k: (v.value if isinstance(v, Enum) else v) for k, v in self.__dict__.items()}
        return {k: v for k, v in d.items() if v not in (None, "")}


@dataclass
class PlanResult:
    """Outcome of executing a plan, with everything the scorer needs."""
    answer: str | None
    evidence: list[Evidence] = field(default_factory=list)
    sufficient: bool = True
    problem: str = ""                    # why the plan failed, for re-planning
    candidates: list[str] = field(default_factory=list)
    incomplete_fields: list[str] = field(default_factory=list)

    @property
    def doc_ids(self) -> list[str]:
        seen, out = set(), []
        for e in self.evidence:
            if e.doc_id not in seen:
                seen.add(e.doc_id)
                out.append(e.doc_id)
        return out


# --------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------

def execute(plan: QueryPlan, g: EventGraph) -> PlanResult:
    """Run a plan against the graph.

    Failures are returned as ``sufficient=False`` with a machine-readable
    ``problem`` string rather than raised, because that string is what the
    agent reads in order to decide what to try next.
    """
    try:
        return _execute(plan, g)
    except Exception as exc:                       # never let a bad plan kill a run
        return PlanResult(None, sufficient=False, problem=f"executor_error: {exc}")


def _execute(plan: QueryPlan, g: EventGraph) -> PlanResult:
    if plan.intent is Intent.FIELD_OF_EVENT:
        ev = g.event_by_title(plan.title or "")
        if not ev:
            return PlanResult(None, sufficient=False,
                              problem=f"no_event_titled: {plan.title}")
        cell = g.field_of(ev, plan.field_name)
        if cell.value is None:
            return PlanResult(None, [cell], sufficient=False,
                              problem=f"field_missing: {plan.field_name}")
        return PlanResult(str(cell.value), [cell])

    if plan.intent in (Intent.COUNT_ABOVE, Intent.ARGMAX):
        if not (plan.sport and plan.games_year and plan.games_season):
            return PlanResult(None, sufficient=False, problem="missing_sport_or_games")
        if plan.intent is Intent.COUNT_ABOVE:
            n, ev, unknown = g.count_above(plan.sport, plan.games_year,
                                           plan.games_season, plan.field_name,
                                           plan.threshold or 0)
            if not ev:
                return PlanResult(None, sufficient=False,
                                  problem=f"no_events_for: {plan.sport} {plan.games_year}")
            return PlanResult(str(n), ev, incomplete_fields=unknown)
        best, ev, unknown = g.argmax(plan.sport, plan.games_year,
                                     plan.games_season, plan.field_name)
        if not best:
            return PlanResult(None, ev, sufficient=False,
                              problem=f"no_events_for: {plan.sport} {plan.games_year}")
        return PlanResult(best.title, ev, incomplete_fields=unknown)

    if plan.intent is Intent.VENUE_DATE:
        hits = g.find_by_venue_date(plan.venue or "", plan.date or "",
                                    plan.games_year, plan.games_season)
        if not hits:
            return PlanResult(None, sufficient=False,
                              problem=f"no_event_at: {plan.venue} / {plan.date}")
        if len(hits) > 1:
            # Ambiguity is reported, not resolved by guessing - the agent tier
            # is what adds a constraint and re-queries.
            return PlanResult(None, [g.field_of(h, plan.answer_field) for h in hits],
                              sufficient=False,
                              problem=f"ambiguous_venue_date: {len(hits)} candidates",
                              candidates=[h.title for h in hits])
        cell = g.field_of(hits[0], plan.answer_field)
        return PlanResult(str(cell.value) if cell.value else None, [cell],
                          sufficient=cell.value is not None,
                          problem="" if cell.value else f"field_missing: {plan.answer_field}")

    if plan.intent is Intent.PREV_EDITION:
        if not (plan.games_year and plan.games_season):
            return PlanResult(None, sufficient=False, problem="missing_games")
        from occam.store.local import _best_by_discipline

        def series_at(year: int) -> tuple[Any, list[str]]:
            pool = [e for e in g.events_in(plan.sport or "", year, plan.games_season or "")
                    if plan.gender is None or e.gender == plan.gender]
            return _best_by_discipline(pool, plan.discipline or ""), [p.title for p in pool]

        # Anchor on the edition named in the question, then follow that page's
        # own PREV_EDITION edge.  Citing the anchor as well as the target is
        # what makes the temporal hop auditable rather than a bare assertion.
        trail: list[Evidence] = []
        anchor, _ = series_at(plan.games_year)
        target = g.prev_edition_of(anchor) if anchor else None
        if anchor:
            trail.append(Evidence(anchor.doc_id, anchor.title, "prev",
                                  anchor.prev_year))

        if target is None:                       # no anchor, or a broken prev edge
            prev = (anchor.prev_year if anchor and anchor.prev_year
                    else g.edition_before(plan.games_year, plan.games_season))
            if not prev:
                return PlanResult(None, trail, sufficient=False,
                                  problem=f"no_edition_before: {plan.games_year}")
            target, pool_titles = series_at(prev)
            if target is None:
                return PlanResult(None, trail, sufficient=False,
                                  problem=(f"ambiguous_discipline: {len(pool_titles)} "
                                           f"candidates in {prev}"),
                                  candidates=pool_titles)

        cell = g.field_of(target, plan.answer_field)
        trail.append(cell)
        return PlanResult(str(cell.value) if cell.value else None, trail,
                          sufficient=cell.value is not None,
                          problem="" if cell.value else f"field_missing: {plan.answer_field}")

    return PlanResult(None, sufficient=False, problem="freeform_requires_text_retrieval")


# --------------------------------------------------------------------------
# Rule-based planner (fast path + reference oracle)
# --------------------------------------------------------------------------

_SEASON_OF_SPORT_HINT = re.compile(
    r"\b(biathlon|luge|skeleton|bobsleigh|curling|ski jumping|nordic combined|"
    r"alpine skiing|cross-country skiing|freestyle skiing|snowboarding|"
    r"figure skating|speed skating|short-track speed skating|ice hockey)\b", re.I)

_RULES: list[tuple[re.Pattern[str], Intent]] = [
    (re.compile(r"^how many (?P<field>nations|competitors) competed in (?P<title>.+?)\?*$", re.I),
     Intent.FIELD_OF_EVENT),
    (re.compile(r"how many (?P<sport>.+?) events at the (?P<year>\d{4}) (?P<season>Summer|Winter) "
                r"Olympics had more than (?P<n>\d+) (?P<field>competitors|nations)", re.I),
     Intent.COUNT_ABOVE),
    (re.compile(r"which (?P<sport>.+?) event at the (?P<year>\d{4}) (?P<season>Summer|Winter) "
                r"Olympics had the (?:highest|largest) number of (?P<field>competitors|nations)", re.I),
     Intent.ARGMAX),
    (re.compile(r"held at (?P<venue>.+?) on (?P<date>.+?)"
                r"(?: at the (?P<year>\d{4}) (?P<season>Summer|Winter) Olympics)?\?*$", re.I),
     Intent.VENUE_DATE),
    (re.compile(r"gold medal in the (?P<disc>.+?) event at the (?P<season>Summer|Winter) "
                r"Olympics held immediately before (?P<year>\d{4})", re.I),
     Intent.PREV_EDITION),
]

# Sport names as they appear in question text, longest first so that
# "short-track speed skating" wins over "speed skating".
_SPORT_WORDS: list[str] = []


def init_sport_vocab(g: EventGraph) -> None:
    """Seed the sport vocabulary from the graph rather than a hard-coded list."""
    global _SPORT_WORDS
    _SPORT_WORDS = sorted({e.sport for e in g.events if e.sport},
                          key=len, reverse=True)


def _gender_of(text: str) -> str | None:
    t = norm_text(text)
    if "mixed" in t:
        return "mixed"
    if re.search(r"\bwomen'?s?\b|\bladies\b", t):
        return "women"
    if re.search(r"\bmen'?s?\b", t):
        return "men"
    return None


def _sport_in(text: str) -> str | None:
    t = norm_text(text)
    for s in _SPORT_WORDS:
        if norm_text(s) in t:
            return s
    return None


def rule_plan(question: str) -> QueryPlan | None:
    """Deterministic plan for question shapes we recognise verbatim.

    This is a *cache*, not the system's understanding: anything it does not
    match goes to the LLM planner.  It exists so the benchmark can show how
    much of the token cost of routine questions is avoidable.
    """
    for pat, intent in _RULES:
        m = pat.search(question)
        if not m:
            continue
        gd = m.groupdict()
        if intent is Intent.FIELD_OF_EVENT:
            return QueryPlan(intent, title=gd["title"].strip(),
                             field_name=gd["field"].lower(), note="rule:field_of_event")
        if intent in (Intent.COUNT_ABOVE, Intent.ARGMAX):
            return QueryPlan(intent, sport=gd["sport"].strip(),
                             games_year=int(gd["year"]), games_season=gd["season"].title(),
                             field_name=gd["field"].lower(),
                             threshold=int(gd["n"]) if gd.get("n") else None,
                             note=f"rule:{intent.value}")
        if intent is Intent.VENUE_DATE:
            return QueryPlan(intent, venue=gd["venue"].strip(), date=gd["date"].strip(),
                             games_year=int(gd["year"]) if gd.get("year") else None,
                             games_season=gd["season"].title() if gd.get("season") else None,
                             answer_field="gold", note="rule:venue_date")
        if intent is Intent.PREV_EDITION:
            disc = gd["disc"].strip()
            return QueryPlan(intent, sport=_sport_in(disc), discipline=disc,
                             gender=_gender_of(disc), games_year=int(gd["year"]),
                             games_season=gd["season"].title(), answer_field="gold",
                             note="rule:prev_edition")
    return None
