"""Planner and executor tests - the contract every pipeline runs through."""
import pytest

from occam.agents.plan import Intent, QueryPlan, execute, init_sport_vocab, rule_plan
from occam.agents.planner import _to_plan
from occam.eval.metrics import answer_matches, score_evidence

DATA = "data/corpus.jsonl"


def test_rule_plan_reads_each_question_shape():
    cases = [
        ("How many nations competed in Judo at the 2016 Summer Olympics?",
         Intent.FIELD_OF_EVENT),
        ("According to the provided corpus, how many cycling events at the 2008 "
         "Summer Olympics had more than 30 competitors?", Intent.COUNT_ABOVE),
        ("According to the provided corpus, which sailing event at the 2016 Summer "
         "Olympics had the highest number of competitors?", Intent.ARGMAX),
        ("Who won the gold medal in the event held at Eton Dorney on 28 July 2012?",
         Intent.VENUE_DATE),
        ("Who won the gold medal in the men's pole vault athletics event at the "
         "Summer Olympics held immediately before 2016?", Intent.PREV_EDITION),
    ]
    for question, intent in cases:
        plan = rule_plan(question)
        assert plan is not None and plan.intent is intent, question


def test_rule_plan_declines_unknown_shapes():
    assert rule_plan("Why did the 1980 boycott happen?") is None


def test_to_plan_accepts_nested_slots():
    """Models read the schema's 'slots:' lines as an instruction to nest."""
    flat = _to_plan({"intent": "field_of_event", "title": "X", "field_name": "nations"})
    nested = _to_plan({"intent": "field_of_event",
                       "slots": {"title": "X", "field_name": "nations"}})
    assert flat.title == nested.title == "X"
    assert flat.field_name == nested.field_name == "nations"


def test_to_plan_rejects_fields_off_the_schema():
    assert _to_plan({"intent": "field_of_event", "field_name": "salary"}).field_name \
        == "competitors"


def test_to_plan_falls_back_on_unknown_intent():
    assert _to_plan({"intent": "teleport"}).intent is Intent.FREEFORM


def test_answer_matches_is_numeric_and_unicode_aware():
    assert answer_matches("5", ["5"])
    assert answer_matches("5.0", ["5"])
    assert answer_matches("Men’s – marathon", ["Men’s - marathon"])
    assert not answer_matches(None, ["5"])
    assert not answer_matches("6", ["5"])


def test_score_evidence_is_a_set_measure():
    s = score_evidence(["a", "b", "c"], ["b", "c", "d"])
    assert s.hits == 2 and s.precision == pytest.approx(2 / 3)
    assert s.recall == pytest.approx(2 / 3)


# -- corpus-backed --------------------------------------------------------

@pytest.fixture(scope="module")
def graph():
    import os
    if not os.path.exists(DATA):
        pytest.skip("run scripts/download_data.py first")
    from occam.ingest.parse import load_events
    from occam.store.local import EventGraph
    g = EventGraph(load_events(DATA)[0])
    init_sport_vocab(g)
    return g


def test_aggregation_counts_and_cites_every_event(graph):
    plan = rule_plan("According to the provided corpus, how many biathlon events at "
                     "the 2018 Winter Olympics had more than 73 competitors?")
    out = execute(plan, graph)
    assert out.answer == "5"
    assert len(out.doc_ids) >= 11        # the count is only checkable with all of them


def test_prev_edition_cites_anchor_and_target(graph):
    plan = rule_plan("Who won the gold medal in the men's 20 kilometres walk athletics "
                     "event at the Summer Olympics held immediately before 2016?")
    out = execute(plan, graph)
    assert out.answer == "Chen Ding"
    assert len(out.doc_ids) == 2         # anchor 2016 page + the 2012 target


def test_ambiguity_is_reported_not_guessed(graph):
    """Two events share this venue and date; guessing one would be a coin flip."""
    plan = QueryPlan(Intent.PREV_EDITION, sport="Taekwondo", discipline="men's 80 kg",
                     gender="men", games_year=2016, games_season="Summer")
    out = execute(plan, graph)
    assert not out.sufficient
    assert out.candidates and "ambiguous" in out.problem


def test_executor_never_raises_on_a_bad_plan(graph):
    out = execute(QueryPlan(Intent.COUNT_ABOVE, sport="Quidditch"), graph)
    assert out.answer is None and not out.sufficient and out.problem
