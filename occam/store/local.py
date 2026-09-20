"""In-memory event graph.

Every method here has a one-to-one counterpart in the GSQL installed by
``occam.store.tigergraph``; this backend exists so the benchmark is runnable
and deterministic without a live cluster, and so TigerGraph results can be
diffed against a reference implementation.

The methods are deliberately shaped like graph traversals rather than table
scans, because they are the tool surface the agent plans over.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from occam.ingest.parse import DateSpan, EventRecord, norm_text, parse_date_field


@dataclass
class Evidence:
    """A single retrieved fact, carrying the doc it came from.

    ``doc_id`` is what the benchmark's ``gold_doc_ids`` are compared against,
    so every answer OCCAM produces can be scored for evidence precision/recall
    rather than answer accuracy alone.
    """
    doc_id: str
    title: str
    field: str
    value: str | int | None

    def cite(self) -> str:
        return f"{self.title} [{self.doc_id}] :: {self.field}={self.value}"


def _spans_match(a: DateSpan | None, b: DateSpan | None) -> bool:
    """True when two date spans agree on every component both of them state.

    The corpus writes ``15-22 August 2004`` where a question may say
    ``15 to 22 August 2004``; normalising to spans lets those meet.  A
    component missing on either side is treated as compatible, not as a
    mismatch, because many pages omit the year.
    """
    if not a or not b:
        return False
    pairs = [(a.start_month, b.start_month), (a.start_day, b.start_day),
             (a.end_month, b.end_month), (a.end_day, b.end_day), (a.year, b.year)]
    stated = [(x, y) for x, y in pairs if x is not None and y is not None]
    return bool(stated) and all(x == y for x, y in stated)


class EventGraph:
    """Indexed view over parsed events, mirroring the TigerGraph schema."""

    def __init__(self, events: Iterable[EventRecord]):
        self.events: list[EventRecord] = list(events)
        self.by_doc: dict[str, EventRecord] = {e.doc_id: e for e in self.events}
        self.by_title: dict[str, EventRecord] = {norm_text(e.title): e for e in self.events}
        self._by_sport_games: dict[tuple[str, int, str], list[EventRecord]] = defaultdict(list)
        self._by_venue: dict[str, list[EventRecord]] = defaultdict(list)
        for e in self.events:
            if e.sport and e.games_year and e.games_season:
                self._by_sport_games[(norm_text(e.sport), e.games_year, e.games_season)].append(e)
            if e.venue:
                self._by_venue[norm_text(e.venue)].append(e)

    # -- vertex lookup ----------------------------------------------------
    def event_by_title(self, title: str) -> EventRecord | None:
        return self.by_title.get(norm_text(title))

    def field_of(self, event: EventRecord, field: str) -> Evidence:
        return Evidence(event.doc_id, event.title, field, getattr(event, field, None))

    # -- HAS_EVENT traversal ----------------------------------------------
    def events_in(self, sport: str, year: int, season: str) -> list[EventRecord]:
        """Games --HAS_EVENT--> Event, filtered to one sport."""
        return list(self._by_sport_games.get((norm_text(sport), year, season), []))

    def sports_at(self, year: int, season: str) -> list[str]:
        return sorted({s for (s, y, sn) in self._by_sport_games if y == year and sn == season})

    # -- aggregation -------------------------------------------------------
    def count_above(self, sport: str, year: int, season: str, field: str,
                    threshold: int) -> tuple[int, list[Evidence], list[str]]:
        """Count events whose numeric `field` exceeds `threshold`.

        Returns the count, the evidence for every event considered (not just
        the matching ones - the full set is what makes the count verifiable),
        and the titles of events whose field is missing, so the caller can
        report incompleteness instead of silently undercounting.
        """
        pool = self.events_in(sport, year, season)
        ev, unknown, n = [], [], 0
        for e in pool:
            val = getattr(e, field, None)
            if val is None:
                unknown.append(e.title)
                continue
            ev.append(Evidence(e.doc_id, e.title, field, val))
            if val > threshold:
                n += 1
        return n, ev, unknown

    def argmax(self, sport: str, year: int, season: str,
               field: str) -> tuple[EventRecord | None, list[Evidence], list[str]]:
        pool = self.events_in(sport, year, season)
        ev, unknown, best = [], [], None
        for e in pool:
            val = getattr(e, field, None)
            if val is None:
                unknown.append(e.title)
                continue
            ev.append(Evidence(e.doc_id, e.title, field, val))
            if best is None or val > getattr(best, field):
                best = e
        return best, ev, unknown

    # -- AT_VENUE traversal ------------------------------------------------
    def events_at_venue(self, venue: str) -> list[EventRecord]:
        """Exact venue match, then containment either way.

        Venue strings drift between question and infobox (``Olympic Tennis
        Centre`` vs ``Athens Olympic Tennis Centre, Athens``), so an exact hit
        is preferred and substring matching is the documented fallback.
        """
        key = norm_text(venue)
        if key in self._by_venue:
            return list(self._by_venue[key])
        return [e for k, evs in self._by_venue.items()
                if key in k or k in key for e in evs]

    def find_by_venue_date(self, venue: str, date: str,
                           year: int | None = None, season: str | None = None
                           ) -> list[EventRecord]:
        """Venue + date -> Event. The core multi-hop retrieval step.

        ``Olympic Stadium`` alone matches 115 events, so the date is what makes
        the lookup selective; exact string match is tried before span match to
        keep precision high.
        """
        pool = self.events_at_venue(venue)
        if year:
            pool = [e for e in pool if e.games_year == year]
        if season:
            pool = [e for e in pool if e.games_season == season]
        key = norm_text(date)
        exact = [e for e in pool if e.date_key == key]
        if exact:
            return exact
        want = parse_date_field(date, year)
        return [e for e in pool if _spans_match(e.date_span, want)]

    # -- PREV_EDITION traversal -------------------------------------------
    def edition_before(self, year: int, season: str) -> int | None:
        """The Games edition immediately preceding `year`.

        Derived from the editions actually present in the corpus rather than
        assuming a fixed four-year cadence, which breaks across the 1992->1994
        Winter split.
        """
        years = {y for (_, y, sn) in self._by_sport_games if sn == season and y < year}
        return max(years) if years else None

    def prev_edition_of(self, event: EventRecord) -> EventRecord | None:
        """Follow the page's own ``prev`` field to the same event one edition back."""
        if not event.prev_year or not event.games_season:
            return None
        return self.match_series(event, event.prev_year, event.games_season)

    def match_series(self, like: EventRecord, year: int, season: str) -> EventRecord | None:
        """Find the same event series at a different Games.

        Matching is on sport + gender + discipline tokens; gender is a hard
        filter because the corpus pairs men's and women's events with nearly
        identical titles, which is the single largest source of wrong answers.
        """
        pool = [e for e in self.events_in(like.sport or "", year, season)
                if e.gender == like.gender]
        return _best_by_discipline(pool, like.discipline or like.title)


def _tokens(s: str) -> set[str]:
    import re
    return {t for t in re.findall(r"[\wÀ-ɏ]+", norm_text(s))
            if t not in {"s", "the", "event", "at", "olympics", "summer", "winter"}}


def _best_by_discipline(pool: list[EventRecord], want: str) -> EventRecord | None:
    """Pick the event whose discipline best overlaps `want`, or None if tied.

    Returning None on a tie is deliberate: an ambiguous match is a signal the
    agent should escalate, not a coin flip to be taken silently.
    """
    if not pool:
        return None
    target = _tokens(want)
    scored = sorted(
        ((len(target & _tokens(e.discipline or e.title)) - 0.01 * len(_tokens(e.discipline or e.title) - target), e)
         for e in pool), key=lambda p: p[0], reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1] if scored[0][0] > 0 else None
