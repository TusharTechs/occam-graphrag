"""LLM planner: natural language question -> QueryPlan over the graph schema.

This is the system's actual understanding.  ``rule_plan`` in
``occam.agents.plan`` is only a cache for question shapes already seen; any
question it does not recognise arrives here, and the agent tier re-enters this
planner with the executor's complaint attached so the next plan is informed by
what went wrong.
"""

from __future__ import annotations

from occam.agents.plan import Intent, QueryPlan
from occam.llm import LLM, extract_json

SCHEMA_DOC = """\
GRAPH SCHEMA (TigerGraph)
  Games(year:int, season:"Summer"|"Winter")
  Event(title, sport, discipline, gender:"men"|"women"|"mixed"|"open",
        venue, date_raw, competitors:int, nations:int,
        gold, silver, bronze, gold_noc, silver_noc, bronze_noc)
  Athlete(name)   Venue(name)   Sport(name)   NOC(code)
  EDGES
    Games -HAS_EVENT-> Event          Event -AT_VENUE-> Venue
    Event -IN_SPORT->  Sport          Event -GOLD|SILVER|BRONZE-> Athlete
    Event -PREV_EDITION-> Event       Event -NEXT_EDITION-> Event

INTENTS (choose exactly one)
  field_of_event  one named event -> one field.
                  slots: title (exact page title), field_name
  count_above     count events of a sport at one Games whose field > threshold.
                  slots: sport, games_year, games_season, field_name, threshold
  argmax          the event of a sport at one Games maximising a field.
                  slots: sport, games_year, games_season, field_name
  venue_date      find the event held at a venue on a date, then read a field.
                  slots: venue, date, (games_year, games_season), answer_field
  prev_edition    the same event series at the Games immediately before a year.
                  slots: sport, discipline, gender, games_year, games_season, answer_field
  freeform        none of the above fit.

RULES
  - field_name / answer_field must be a real Event field, e.g. competitors,
    nations, gold, silver, bronze.
  - "who won the gold medal" -> answer_field "gold".
  - games_season is "Summer" or "Winter". Winter sports include biathlon, luge,
    skeleton, bobsleigh, curling, ski jumping, nordic combined, alpine skiing,
    cross-country skiing, freestyle skiing, snowboarding, figure skating,
    speed skating, short-track speed skating, ice hockey.
  - Copy venue and date EXACTLY as written in the question; do not reformat.
  - gender must be inferred from wording such as "men's" / "women's" / "mixed".
  - Reply with ONE FLAT JSON object: put every slot at the top level,
    do NOT nest them under a "slots" key, and emit nothing else."""

_PROMPT = """{schema}

SPORT VOCABULARY (use these exact spellings for `sport`):
{sports}

QUESTION: {question}
{feedback}
JSON plan:"""

_SYSTEM = ("You translate questions into structured query plans over an Olympic "
           "knowledge graph. You never answer the question yourself; you only "
           "produce the plan that would retrieve the answer.")


def plan_with_llm(question: str, llm: LLM, sports: list[str],
                  feedback: str | None = None) -> tuple[QueryPlan, object]:
    """Ask the model for a plan. Returns the plan and the raw LLM response.

    `feedback` carries the executor's complaint from a previous attempt (for
    example ``ambiguous_venue_date: 2 candidates``) so the agent's second plan
    is a genuine revision rather than a retry of the same thing.
    """
    fb = ""
    if feedback:
        fb = (f"\nA PREVIOUS PLAN FAILED. Problem: {feedback}\n"
              "Write a different plan that resolves this. If the failure was "
              "ambiguity, add the constraint that separates the candidates.\n")
    prompt = _PROMPT.format(schema=SCHEMA_DOC, sports=", ".join(sports),
                            question=question, feedback=fb)
    resp = llm.complete(prompt, system=_SYSTEM, max_output_tokens=400)
    return _to_plan(extract_json(resp.text)), resp


_ALLOWED_FIELDS = {"competitors", "nations", "gold", "silver", "bronze",
                   "gold_noc", "silver_noc", "bronze_noc", "venue", "date_raw",
                   "title", "discipline", "sport"}


def _to_plan(d: dict) -> QueryPlan:
    """Coerce a model reply into a QueryPlan, rejecting fields off the schema."""
    # The schema lists each intent's inputs as "slots: ...", which models
    # reasonably read as an instruction to nest them under a "slots" key.
    # Accept either shape rather than losing every field to a wrapper.
    if isinstance(d.get("slots"), dict):
        d = {**d, **d["slots"]}

    try:
        intent = Intent(str(d.get("intent", "freeform")).strip())
    except ValueError:
        intent = Intent.FREEFORM

    def s(key: str) -> str | None:
        v = d.get(key)
        return str(v).strip() if v not in (None, "") else None

    def i(key: str) -> int | None:
        v = d.get(key)
        try:
            return int(str(v).strip())
        except (TypeError, ValueError):
            return None

    field_name = (s("field_name") or "competitors").lower()
    answer_field = (s("answer_field") or "gold").lower()
    season = s("games_season")
    gender = s("gender")
    return QueryPlan(
        intent=intent,
        title=s("title"),
        sport=s("sport"),
        games_year=i("games_year"),
        games_season=season.title() if season else None,
        gender=gender.lower() if gender else None,
        discipline=s("discipline"),
        venue=s("venue"),
        date=s("date"),
        field_name=field_name if field_name in _ALLOWED_FIELDS else "competitors",
        threshold=i("threshold"),
        answer_field=answer_field if answer_field in _ALLOWED_FIELDS else "gold",
        note="llm",
    )
