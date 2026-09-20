"""Structured extraction from the hackathon corpus.

The corpus is Wikipedia plain text where Olympic event pages carry an
``[Infobox Olympic event]`` block.  Every question in the benchmark is
answerable from those infobox fields, so extraction fidelity - not retrieval
cleverness - is what sets the accuracy ceiling.  This module is deliberately
strict: a field that cannot be parsed confidently is left ``None`` rather than
guessed, so downstream aggregation can report incompleteness instead of
inventing a count.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterator

# Wikipedia mixes en dashes, em dashes, hyphens and non-breaking spaces fairly
# freely; every comparison in OCCAM goes through `norm_text` first.
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
_SPACES = dict.fromkeys(map(ord, "       "), " ")

INFOBOX_RE = re.compile(r"^\[Infobox ([^\]]+)\]\s*$", re.M)
FIELD_RE = re.compile(r"^\s{2}(\w+):[ \t]*(.*)$", re.M)
TITLE_SPLIT_RE = re.compile(r"\s+[-–—]\s+")
GAMES_RE = re.compile(r"\b((?:19|20)\d{2})\s+(Summer|Winter)\b")

MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"], start=1)
}
MONTH_RE = re.compile(r"\b(" + "|".join(MONTHS) + r")\b", re.I)
YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
DAY_RE = re.compile(r"\b(\d{1,2})\b")


def norm_text(s: str | None) -> str:
    """Casefold + collapse unicode punctuation so corpus and question text meet."""
    if not s:
        return ""
    s = unicodedata.normalize("NFC", s).translate(_SPACES).translate(_DASHES)
    return re.sub(r"\s+", " ", s).strip().lower()


def _read_block(text: str, start: int) -> dict[str, str]:
    """Read the contiguous indented ``key: value`` block beginning at `start`.

    Prose that happens to contain a colon must not leak in as a field, so the
    first non-blank line that is not an indented field ends the block.
    """
    fields: dict[str, str] = {}
    for line in text[start:].splitlines():
        if not line.strip():
            if fields:  # a blank line after fields ends the infobox
                break
            continue
        fm = FIELD_RE.match(line)
        if not fm:
            break
        key, val = fm.group(1), fm.group(2).strip()
        if val:
            fields[key] = val
    return fields


def parse_infoboxes(text: str) -> list[tuple[str, dict[str, str]]]:
    """Return *every* infobox in the document, in order.

    Some pages stack two templates - the 25 tennis pages open with an
    ``[Infobox tennis tournament event]`` and only then carry the
    ``[Infobox Olympic event]`` block holding venue, date and medallists.
    Reading just the first infobox silently loses those fields.
    """
    return [(m.group(1).strip(), _read_block(text, m.end()))
            for m in INFOBOX_RE.finditer(text)]


def parse_infobox(text: str) -> tuple[str | None, dict[str, str]]:
    """The Olympic-event infobox if the page has one, else the first infobox."""
    boxes = parse_infoboxes(text)
    if not boxes:
        return None, {}
    for kind, fields in boxes:
        if "olympic event" in kind.lower():
            return kind, fields
    return boxes[0]


# Name particles that legitimately sit mid-name before a capital letter, so a
# lowercase->uppercase boundary after them is not a roster separator.
_PARTICLE_RE = re.compile(
    r"(?:\b(?:Mc|Mac|O'|D'|L'|de|De|van|Van|von|Von|di|Di|da|Da|du|Du|la|La|le|Le|del|Del|dos|Dos|ten|Ten|ter|Ter)|['’-])$"
)


def _roster_fragments(s: str) -> list[str]:
    """Split at lowercase->uppercase boundaries, Unicode-correctly.

    A character-class range such as ``[\\u00c0-\\u024f]`` spans Latin Extended-A
    and so contains lowercase letters too, which wrongly splits names like
    ``Süleymanoglu`` mid-word.  Testing ``str.isupper()`` per character is the
    only reliable test across scripts.
    """
    out, start = [], 0
    for i in range(1, len(s)):
        prev, cur = s[i - 1], s[i]
        if cur.isupper() and (prev.islower() or prev == "."):
            out.append(s[start:i])
            start = i
    out.append(s[start:])
    return out


def split_medalists(raw: str | None) -> list[str]:
    """Split run-together team rosters (``Dani KingLaura TrottJoanna Rowsell``).

    The corpus concatenates team members with no separator, so the only signal
    is a lowercase->uppercase boundary.  That boundary also occurs *inside*
    names like ``McDonald`` or ``van Dijk``, so a fragment is merged back when
    the previous piece is not yet a complete name or ends in a name particle.

    Answers are graded against the verbatim string, so callers keep `raw` for
    answering and use this only for building Athlete vertices.
    """
    if not raw or not raw.strip():
        return []
    out: list[str] = []
    for frag in _roster_fragments(raw.strip()):
        if out and (" " not in out[-1].strip() or _PARTICLE_RE.search(out[-1])):
            out[-1] += frag          # still mid-name: rejoin
        else:
            out.append(frag)
    return [o.strip() for o in out if o.strip()]


@dataclass
class DateSpan:
    """A resolved calendar span. ``year`` may be None when the field omits it."""
    start_month: int | None = None
    start_day: int | None = None
    end_month: int | None = None
    end_day: int | None = None
    year: int | None = None


def parse_date_field(raw: str | None, fallback_year: int | None = None) -> DateSpan:
    """Best-effort structuring of the wildly inconsistent ``date``/``dates`` field.

    Seen in the corpus: ``4 August 2012``, ``6 to 8 August``, ``23-26 August``,
    ``February 22, 1992``, ``28 July - 4 August 2012`` and run-together
    multi-session strings like ``August 18 (heats)August 20 (final)``.
    Exact string matching handles most questions; this gives the agent a
    structured fallback when the verbatim form differs.
    """
    span = DateSpan(year=fallback_year)
    if not raw:
        return span
    s = norm_text(re.sub(r"\([^)]*\)", " ", raw))  # drop "(heats)" annotations
    years = YEAR_RE.findall(s)
    if years:
        span.year = int(years[0])
    months = [MONTHS[m.lower()] for m in MONTH_RE.findall(s)]
    days = [int(d) for d in DAY_RE.findall(re.sub(r"\b(?:19|20)\d{2}\b", " ", s))
            if 1 <= int(d) <= 31]
    if months:
        span.start_month = months[0]
        span.end_month = months[-1]
    if days:
        span.start_day = days[0]
        span.end_day = days[-1]
    return span


@dataclass
class EventRecord:
    """One Olympic event page, flattened into the graph's property model."""
    doc_id: str
    title: str
    url: str
    approx_tokens: int
    sport: str | None = None
    discipline: str | None = None
    gender: str | None = None          # men | women | mixed | open
    games_year: int | None = None
    games_season: str | None = None    # Summer | Winter
    venue: str | None = None
    date_raw: str | None = None
    date_key: str | None = None
    date_span: DateSpan | None = None
    competitors: int | None = None
    nations: int | None = None
    gold: str | None = None
    silver: str | None = None
    bronze: str | None = None
    gold_noc: str | None = None
    silver_noc: str | None = None
    bronze_noc: str | None = None
    prev_year: int | None = None
    next_year: int | None = None
    raw_fields: dict[str, str] = field(default_factory=dict)

    @property
    def games(self) -> str | None:
        if self.games_year and self.games_season:
            return f"{self.games_year} {self.games_season}"
        return None

    def to_json(self) -> dict:
        d = asdict(self)
        d["date_span"] = asdict(self.date_span) if self.date_span else None
        d["games"] = self.games
        return d


def _gender_from(discipline: str | None, title: str) -> str | None:
    hay = norm_text(f"{discipline or ''} {title}")
    if "mixed" in hay:
        return "mixed"
    if re.search(r"\bwomen'?s?\b|\bladies\b", hay):
        return "women"
    if re.search(r"\bmen'?s?\b", hay):
        return "men"
    return "open"


def _int_or_none(v: str | None) -> int | None:
    if not v:
        return None
    m = re.match(r"^\s*(\d+)", v.replace(",", ""))
    return int(m.group(1)) if m else None


def parse_event(doc: dict) -> EventRecord | None:
    """Parse one corpus row into an EventRecord, or None if it is not an event page."""
    kind, fields = parse_infobox(doc.get("text", ""))
    if not kind or "olympic event" not in kind.lower():
        return None

    title = doc["title"]
    head, _, tail = title.partition(" at the ")
    parts = TITLE_SPLIT_RE.split(tail, maxsplit=1)
    discipline = parts[1].strip() if len(parts) > 1 else fields.get("event")

    rec = EventRecord(
        doc_id=doc["doc_id"],
        title=title,
        url=doc.get("url", ""),
        approx_tokens=doc.get("approx_tokens", 0),
        sport=head.strip() or None,
        discipline=discipline,
        raw_fields=fields,
    )
    rec.gender = _gender_from(discipline, title)

    gm = GAMES_RE.search(fields.get("games", "") or tail)
    if gm:
        rec.games_year, rec.games_season = int(gm.group(1)), gm.group(2)

    rec.venue = fields.get("venue") or (fields.get("venues") or None)
    rec.date_raw = fields.get("date") or fields.get("dates")
    rec.date_key = norm_text(rec.date_raw)
    rec.date_span = parse_date_field(rec.date_raw, rec.games_year)

    rec.competitors = _int_or_none(fields.get("competitors"))
    rec.nations = _int_or_none(fields.get("nations"))
    for slot in ("gold", "silver", "bronze"):
        setattr(rec, slot, fields.get(slot))
        setattr(rec, f"{slot}_noc", fields.get(f"{slot}NOC"))
    rec.prev_year = _int_or_none(fields.get("prev"))
    rec.next_year = _int_or_none(fields.get("next"))
    return rec


def iter_corpus(path: str | Path) -> Iterator[dict]:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def load_events(path: str | Path) -> tuple[list[EventRecord], list[dict]]:
    """Split the corpus into parsed Olympic events and everything else.

    The ~740 non-event documents are distractors for the provided questions but
    are still indexed for the RAG pipeline, because punishing naive similarity
    search is exactly what they are there for.
    """
    events: list[EventRecord] = []
    others: list[dict] = []
    for doc in iter_corpus(path):
        rec = parse_event(doc)
        if rec:
            events.append(rec)
        else:
            others.append(doc)
    return events, others
