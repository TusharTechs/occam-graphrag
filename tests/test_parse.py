"""Parser tests.

Extraction sets the accuracy ceiling on this benchmark, so these lock down the
two bugs that cost real answers plus the field-level contract the graph relies
on. Corpus-backed tests skip when data/ has not been downloaded.
"""
import pytest

from occam.ingest.parse import (norm_text, parse_date_field, parse_event,
                                parse_infoboxes, split_medalists)

DATA = "data/corpus.jsonl"


def test_norm_text_folds_dashes_and_spaces():
    assert norm_text("Men’s – 100 m") == "men’s - 100 m"


@pytest.mark.parametrize("raw,expected", [
    ("Dani KingLaura TrottJoanna Rowsell",
     ["Dani King", "Laura Trott", "Joanna Rowsell"]),
    ("Erik LesserDaniel BöhmArnd PeifferSimon Schempp",
     ["Erik Lesser", "Daniel Böhm", "Arnd Peiffer", "Simon Schempp"]),
    ("Chen Ding", ["Chen Ding"]),
])
def test_split_medalists_splits_rosters(raw, expected):
    assert split_medalists(raw) == expected


@pytest.mark.parametrize("name", [
    "Naim Süleymanoğlu",   # g-breve is not uppercase, despite its code point
    "Ryan McDonald",                 # Mc is a particle, not a roster boundary
    "Virgil van Dijk",
    "Ole Einar Bjørndalen",
])
def test_split_medalists_keeps_single_names_whole(name):
    assert split_medalists(name) == [name]


def test_parse_infoboxes_returns_every_box():
    text = ("[Infobox tennis tournament event]\n  champ: A B\n\n"
            "[Infobox Olympic event]\n  venue: Somewhere\n  gold: C D\n\nProse here.")
    boxes = parse_infoboxes(text)
    assert [k for k, _ in boxes] == ["tennis tournament event", "Olympic event"]
    assert boxes[1][1]["gold"] == "C D"


def test_prose_colons_do_not_become_fields():
    text = "[Infobox Olympic event]\n  gold: A B\n\nThe final: a close race.\n"
    _, fields = parse_infoboxes(text)[0]
    assert set(fields) == {"gold"}


@pytest.mark.parametrize("raw,month,start,end", [
    ("4 August 2012", 8, 4, 4),
    ("6 to 8 August", 8, 6, 8),
    ("23–26 August", 8, 23, 26),
    ("February 22, 1992", 2, 22, 22),
    ("15–22 August 2004", 8, 15, 22),
])
def test_parse_date_field_handles_corpus_formats(raw, month, start, end):
    s = parse_date_field(raw)
    assert (s.start_month, s.start_day, s.end_day) == (month, start, end)


def test_parse_date_field_ignores_session_annotations():
    s = parse_date_field("August 18 (heats)August 20 (final)")
    assert s.start_month == 8 and s.start_day == 18 and s.end_day == 20


def test_parse_event_ignores_non_olympic_pages():
    assert parse_event({"doc_id": "x", "title": "Some Film",
                        "text": "[Infobox film]\n  director: A B\n"}) is None


# -- corpus-backed --------------------------------------------------------

@pytest.fixture(scope="module")
def events():
    import os
    if not os.path.exists(DATA):
        pytest.skip("run scripts/download_data.py first")
    from occam.ingest.parse import load_events
    return load_events(DATA)[0]


def test_corpus_parses_expected_volume(events):
    assert len(events) > 2150


def test_tennis_pages_recover_the_second_infobox(events):
    """The tennis template hides venue/date/gold behind a second infobox."""
    ev = next(e for e in events
              if e.title == "Tennis at the 2004 Summer Olympics – Men's singles")
    assert ev.venue and ev.date_raw and ev.gold == "Nicolás Massú"
    assert ev.competitors == 64


def test_key_fields_are_widely_populated(events):
    n = len(events)
    assert sum(1 for e in events if e.competitors is not None) / n > 0.97
    assert sum(1 for e in events if e.gold) / n > 0.98
    assert sum(1 for e in events if e.games) / n > 0.99


def test_gender_is_inferred(events):
    genders = {e.gender for e in events}
    assert genders <= {"men", "women", "mixed", "open"}
    assert sum(1 for e in events if e.gender == "men") > 1000
