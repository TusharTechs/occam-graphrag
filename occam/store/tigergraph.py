"""TigerGraph backend: schema, loading and the GSQL behind each agent tool.

The local store in ``occam.store.local`` is the reference implementation; this
module puts the same model in TigerGraph so the agent's tools run as real
traversals and aggregations, with chunk embeddings stored as vertex attributes
(TigerVector) rather than in a separate vector service.  Keeping vectors beside
the graph is the point: a filtered vector search can run *inside* a traversal
with no cross-system join.

Connection settings come from the environment (see ``.env.example``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from occam.ingest.parse import EventRecord, split_medalists

SCHEMA_GSQL = """
# Global vertex and edge types must be created in the global scope; without
# USE GLOBAL the first CREATE VERTEX is rejected.
USE GLOBAL

CREATE VERTEX Games (
    PRIMARY_ID gid STRING, year INT, season STRING
) WITH primary_id_as_attribute="true"

CREATE VERTEX Sport (PRIMARY_ID name STRING) WITH primary_id_as_attribute="true"
CREATE VERTEX Venue (PRIMARY_ID name STRING) WITH primary_id_as_attribute="true"
CREATE VERTEX Athlete (PRIMARY_ID name STRING) WITH primary_id_as_attribute="true"
CREATE VERTEX NOC (PRIMARY_ID code STRING) WITH primary_id_as_attribute="true"

CREATE VERTEX Event (
    PRIMARY_ID doc_id STRING,
    title STRING, url STRING,
    sport STRING, discipline STRING, gender STRING,
    games_year INT, games_season STRING,
    venue STRING, date_raw STRING,
    competitors INT, nations INT,
    has_competitors BOOL, has_nations BOOL,
    gold STRING, silver STRING, bronze STRING,
    gold_noc STRING, silver_noc STRING, bronze_noc STRING,
    prev_year INT, next_year INT
) WITH primary_id_as_attribute="true"

CREATE VERTEX Chunk (
    PRIMARY_ID chunk_id STRING, doc_id STRING, title STRING, text STRING
) WITH primary_id_as_attribute="true"

CREATE DIRECTED EDGE HAS_EVENT   (FROM Games,  TO Event) WITH REVERSE_EDGE="EVENT_OF"
CREATE DIRECTED EDGE AT_VENUE    (FROM Event,  TO Venue) WITH REVERSE_EDGE="HOSTED"
CREATE DIRECTED EDGE IN_SPORT    (FROM Event,  TO Sport) WITH REVERSE_EDGE="SPORT_OF"
CREATE DIRECTED EDGE WON_GOLD    (FROM Event,  TO Athlete) WITH REVERSE_EDGE="GOLD_IN"
CREATE DIRECTED EDGE WON_SILVER  (FROM Event,  TO Athlete) WITH REVERSE_EDGE="SILVER_IN"
CREATE DIRECTED EDGE WON_BRONZE  (FROM Event,  TO Athlete) WITH REVERSE_EDGE="BRONZE_IN"
CREATE DIRECTED EDGE REPRESENTS  (FROM Athlete, TO NOC)   WITH REVERSE_EDGE="REPRESENTED_BY"
CREATE DIRECTED EDGE PREV_EDITION(FROM Event,  TO Event)  WITH REVERSE_EDGE="NEXT_EDITION"
CREATE DIRECTED EDGE SOURCED_FROM(FROM Chunk,  TO Event)  WITH REVERSE_EDGE="HAS_CHUNK"

CREATE GRAPH {graph} ({types})
"""

# The graph enumerates its own types rather than using (*). On a shared
# instance - Savanna ships a pre-loaded Transaction_Fraud solution - the
# wildcard would pull every global vertex and edge on the server into this
# graph, fraud schema included.
GRAPH_TYPES = [
    "Games", "Sport", "Venue", "Athlete", "NOC", "Event", "Chunk",
    "HAS_EVENT", "AT_VENUE", "IN_SPORT", "WON_GOLD", "WON_SILVER",
    "WON_BRONZE", "REPRESENTS", "PREV_EDITION", "SOURCED_FROM",
]


def schema_gsql(graph: str) -> str:
    """The schema script for `graph`, with its type list filled in."""
    return SCHEMA_GSQL.format(graph=graph, types=", ".join(GRAPH_TYPES))

# Embeddings live on Chunk as a TigerVector attribute so similarity search and
# graph filters run in the same engine.
VECTOR_GSQL = """
USE GRAPH {graph}
CREATE SCHEMA_CHANGE JOB add_vectors FOR GRAPH {graph} {{
    ALTER VERTEX Chunk ADD VECTOR ATTRIBUTE emb(dimension={dim}, metric="COSINE");
}}
RUN SCHEMA_CHANGE JOB add_vectors
"""

# Each script opens with USE GRAPH: GSQL rejects CREATE QUERY without a graph
# context even though the statement names the graph in its FOR GRAPH clause.
# One installed query per agent tool. Aggregation and argmax run entirely in
# the database - the point of the graph tier is that the LLM never sees the
# 8-43 documents these questions span.
QUERIES_GSQL = {
    "count_above": """
USE GRAPH {graph}
CREATE OR REPLACE DISTRIBUTED QUERY count_above(
    STRING sport, INT yr, STRING season, INT threshold) FOR GRAPH {graph} {{
  SumAccum<INT> @@matched;
  SumAccum<INT> @@unknown;
  SetAccum<STRING> @@docs;
  Seed = {{Event.*}};
  R = SELECT e FROM Seed:e
      WHERE lower(e.sport) == lower(sport)
        AND e.games_year == yr AND e.games_season == season
      ACCUM
        @@docs += e.doc_id,
        CASE WHEN e.has_competitors THEN
          CASE WHEN e.competitors > threshold THEN @@matched += 1 END
        ELSE @@unknown += 1 END;
  # "count" is a GSQL reserved word and cannot be used as an alias.
  PRINT @@matched AS matched, @@unknown AS missing_field, @@docs AS evidence;
}}""",
    "argmax_competitors": """
USE GRAPH {graph}
CREATE OR REPLACE DISTRIBUTED QUERY argmax_competitors(
    STRING sport, INT yr, STRING season) FOR GRAPH {graph} {{
  MaxAccum<INT> @@best;
  SetAccum<STRING> @@docs;
  Seed = {{Event.*}};
  R = SELECT e FROM Seed:e
      WHERE lower(e.sport) == lower(sport)
        AND e.games_year == yr AND e.games_season == season AND e.has_competitors
      ACCUM @@best += e.competitors, @@docs += e.doc_id;
  Best = SELECT e FROM R:e WHERE e.competitors == @@best;
  PRINT Best, @@docs AS evidence;
}}""",
    "event_at_venue_date": """
USE GRAPH {graph}
CREATE OR REPLACE DISTRIBUTED QUERY event_at_venue_date(
    STRING venue_name, STRING date_str) FOR GRAPH {graph} {{
  Seed = {{Venue.*}};
  V = SELECT v FROM Seed:v WHERE lower(v.name) == lower(venue_name);
  E = SELECT e FROM V:v -(HOSTED:h)- Event:e
      WHERE lower(e.date_raw) == lower(date_str);
  PRINT E;
}}""",
    "event_by_title": """
USE GRAPH {graph}
CREATE OR REPLACE DISTRIBUTED QUERY event_by_title(STRING t) FOR GRAPH {graph} {{
  Seed = {{Event.*}};
  E = SELECT e FROM Seed:e WHERE lower(e.title) == lower(t);
  PRINT E;
}}""",
    "prev_edition": """
USE GRAPH {graph}
CREATE OR REPLACE DISTRIBUTED QUERY prev_edition(VERTEX<Event> ev) FOR GRAPH {graph} {{
  Start = {{ev}};
  P = SELECT p FROM Start:e -(PREV_EDITION:r)- Event:p;
  PRINT Start AS anchor, P AS previous;
}}""",
}


@dataclass
class TGConfig:
    host: str
    graph: str
    username: str
    password: str
    secret: str = ""

    @classmethod
    def from_env(cls, require: bool = True) -> "TGConfig":
        """Read connection settings. ``require=False`` yields placeholders so
        ``--dry-run`` can print the GSQL without a cluster to connect to."""
        missing = [k for k in ("TG_HOST", "TG_GRAPH") if not os.environ.get(k)]
        if missing and require:
            raise RuntimeError(f"missing TigerGraph settings: {', '.join(missing)}")
        if missing:
            return cls(host=os.environ.get("TG_HOST", "<TG_HOST>"),
                       graph=os.environ.get("TG_GRAPH", "OlympicKG"),
                       username="", password="")
        return cls(host=os.environ["TG_HOST"], graph=os.environ["TG_GRAPH"],
                   username=os.environ.get("TG_USERNAME", "tigergraph"),
                   password=os.environ.get("TG_PASSWORD", ""),
                   secret=os.environ.get("TG_SECRET", ""))


def connect(cfg: TGConfig | None = None, with_graph: bool = True):
    """Open an authenticated pyTigerGraph connection.

    ``with_graph=False`` omits the graph name, which is required for the very
    first call: naming a graph that does not exist yet fails, and the schema
    step is precisely when it does not exist. A RESTPP token also cannot be
    issued before the graph is there, so that is skipped too.
    """
    from occam.net import ensure_tls_trust
    cfg = cfg or TGConfig.from_env()
    ensure_tls_trust(cfg.host.split("//")[-1].split("/")[0])
    import pyTigerGraph as tg
    kwargs = dict(host=cfg.host, username=cfg.username, password=cfg.password)
    if with_graph:
        kwargs["graphname"] = cfg.graph
    if cfg.secret:
        kwargs["gsqlSecret"] = cfg.secret
    conn = tg.TigerGraphConnection(**kwargs)
    if cfg.secret and with_graph:
        try:
            conn.getToken(cfg.secret)
        except Exception as exc:          # token is only needed for data calls
            print(f"    note: could not mint a RESTPP token yet ({exc})")
    return conn


def event_vertex(rec: EventRecord) -> tuple[str, dict[str, Any]]:
    """One Event vertex payload.

    ``has_competitors`` / ``has_nations`` are stored explicitly because GSQL
    has no NULL: without them a missing field would read as 0 and quietly
    corrupt every aggregation.
    """
    return rec.doc_id, {
        "title": rec.title, "url": rec.url,
        "sport": rec.sport or "", "discipline": rec.discipline or "",
        "gender": rec.gender or "", "games_year": rec.games_year or 0,
        "games_season": rec.games_season or "",
        "venue": rec.venue or "", "date_raw": rec.date_raw or "",
        "competitors": rec.competitors or 0, "nations": rec.nations or 0,
        "has_competitors": rec.competitors is not None,
        "has_nations": rec.nations is not None,
        "gold": rec.gold or "", "silver": rec.silver or "", "bronze": rec.bronze or "",
        "gold_noc": rec.gold_noc or "", "silver_noc": rec.silver_noc or "",
        "bronze_noc": rec.bronze_noc or "",
        "prev_year": rec.prev_year or 0, "next_year": rec.next_year or 0,
    }


def load_events(conn, events: list[EventRecord], batch: int = 1000) -> dict[str, int]:
    """Upsert every vertex and edge derived from the parsed events.

    Edges are grouped by (source type, edge type, target type) and sent with
    upsertEdges rather than one call each: the corpus yields well over 13,000
    edges, and a round trip apiece turns a one-minute load into an hour.
    """
    from collections import defaultdict

    counts: dict[str, int] = defaultdict(int)
    games: dict[str, dict] = {}
    sports: set[str] = set()
    venues: set[str] = set()
    athletes: set[str] = set()
    nocs: set[str] = set()
    ev_rows: list = []
    edges: dict[tuple[str, str, str], list] = defaultdict(list)
    by_series: dict[tuple, dict[int, str]] = {}
    by_doc = {e.doc_id: e for e in events}

    for rec in events:
        ev_rows.append(event_vertex(rec))
        if rec.games:
            games[rec.games] = {"year": rec.games_year, "season": rec.games_season}
            edges[("Games", "HAS_EVENT", "Event")].append((rec.games, rec.doc_id, {}))
        if rec.sport:
            sports.add(rec.sport)
            edges[("Event", "IN_SPORT", "Sport")].append((rec.doc_id, rec.sport, {}))
        if rec.venue:
            venues.add(rec.venue)
            edges[("Event", "AT_VENUE", "Venue")].append((rec.doc_id, rec.venue, {}))
        for slot, etype in (("gold", "WON_GOLD"), ("silver", "WON_SILVER"),
                            ("bronze", "WON_BRONZE")):
            noc = getattr(rec, f"{slot}_noc")
            for name in split_medalists(getattr(rec, slot)):
                athletes.add(name)
                edges[("Event", etype, "Athlete")].append((rec.doc_id, name, {}))
                if noc:
                    edges[("Athlete", "REPRESENTS", "NOC")].append((name, noc, {}))
            if noc:
                nocs.add(noc)
        key = (rec.sport, rec.discipline, rec.gender, rec.games_season)
        if rec.games_year:
            by_series.setdefault(key, {})[rec.games_year] = rec.doc_id

    # PREV_EDITION is materialised from each page's own `prev` year inside its
    # own series, so the temporal hop is a single edge rather than a scan.
    for series in by_series.values():
        for doc_id in series.values():
            target = series.get(by_doc[doc_id].prev_year or -1)
            if target:
                edges[("Event", "PREV_EDITION", "Event")].append((doc_id, target, {}))

    def send_vertices(kind: str, rows: list) -> None:
        for i in range(0, len(rows), batch):
            conn.upsertVertices(kind, rows[i:i + batch])
        counts[kind] += len(rows)

    send_vertices("Event", ev_rows)
    send_vertices("Games", [(k, v) for k, v in games.items()])
    send_vertices("Sport", [(s, {}) for s in sorted(sports)])
    send_vertices("Venue", [(v, {}) for v in sorted(venues)])
    send_vertices("Athlete", [(a, {}) for a in sorted(athletes)])
    send_vertices("NOC", [(n, {}) for n in sorted(nocs)])

    for (src, etype, tgt), rows in edges.items():
        uniq = list({(s, d): (s, d, a) for s, d, a in rows}.values())
        for i in range(0, len(uniq), batch):
            conn.upsertEdges(src, etype, tgt, uniq[i:i + batch])
        counts[etype] += len(uniq)
    return dict(counts)


# --------------------------------------------------------------------------
# Query execution - the same surface as occam.store.local.EventGraph
# --------------------------------------------------------------------------

class TigerGraphBackend:
    """Runs the installed GSQL behind each agent tool.

    Method names and return shapes mirror ``EventGraph`` so the two can be
    compared directly; ``scripts/verify_tigergraph.py`` asserts they agree.
    """

    def __init__(self, conn):
        self.conn = conn

    def _run(self, name: str, **params):
        # A query's first execution after install pays a cold-start cost, so the
        # budget is generous; the aggregations themselves run in milliseconds.
        return self.conn.runInstalledQuery(name, params=params, timeout=300_000)

    def count_above(self, sport: str, year: int, season: str,
                    threshold: int) -> tuple[int, list[str], int]:
        """Count events over a threshold. Returns (count, evidence doc ids, missing)."""
        out = self._run("count_above", sport=sport, yr=year, season=season,
                        threshold=threshold)
        merged: dict = {}
        for block in out:
            merged.update(block)
        return (int(merged.get("matched", 0)),
                list(merged.get("evidence", [])),
                int(merged.get("missing_field", 0)))

    def argmax_competitors(self, sport: str, year: int,
                           season: str) -> tuple[str | None, list[str]]:
        out = self._run("argmax_competitors", sport=sport, yr=year, season=season)
        title, evidence = None, []
        for block in out:
            for key, val in block.items():
                if key == "evidence":
                    evidence = list(val)
                elif isinstance(val, list) and val and isinstance(val[0], dict):
                    title = val[0].get("attributes", {}).get("title")
        return title, evidence

    def event_at_venue_date(self, venue: str, date: str) -> list[dict]:
        out = self._run("event_at_venue_date", venue_name=venue, date_str=date)
        rows: list[dict] = []
        for block in out:
            for val in block.values():
                if isinstance(val, list):
                    rows.extend(v.get("attributes", {}) for v in val
                                if isinstance(v, dict))
        return rows

    def event_by_title(self, title: str) -> dict | None:
        """One Event's attributes, looked up by its exact page title."""
        out = self._run("event_by_title", t=title)
        for block in out:
            for val in block.values():
                if isinstance(val, list) and val:
                    return val[0].get("attributes", {})
        return None

    def prev_edition(self, doc_id: str) -> dict | None:
        out = self._run("prev_edition", ev=doc_id)
        for block in out:
            prev = block.get("previous")
            if isinstance(prev, list) and prev:
                return prev[0].get("attributes", {})
        return None

    def stats(self) -> dict[str, int]:
        """Vertex counts, for confirming a load actually landed."""
        return {v: self.conn.getVertexCount(v)
                for v in ("Games", "Event", "Venue", "Sport", "Athlete", "NOC")}
