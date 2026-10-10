"""A historical report can consume only the complete operation it actually covers."""

import pytest

from app.guide.steps import matches_reported, user_reported_actions


def reported(value, **extra):
    return user_reported_actions({"active_issue_id": "i", "issues": {"i": {"facts": [{
        "kind": "action_taken", "status": "active", "polarity": "affirmed", "source_kind": "user_report",
        "value": value, **extra,
    }]}}})


@pytest.mark.parametrize("value", ["cleaned it", "cleaned everything", "cleaned", "new filter", "tank full", "ran a cleaning task near the contacts"])
@pytest.mark.parametrize("instruction", ["Clean the contacts.", "Replace the filter.", "Refill the tank.",
                                         "Press the tank lid and start a cleaning task."])
def test_vague_objects_and_descriptive_words_never_consume_an_operation(value, instruction):
    assert matches_reported(instruction, reported(value)) is None


@pytest.mark.parametrize("instruction", ["Clean the contacts and inspect the cable.", "Clean the contacts, then remove the cover.",
                                         "Clean the contacts and the tray.", "Clean and replace the filter.",
                                         "Clean the contacts. Please upload a photo.", "Clean the contacts. Does it work?"])
def test_partial_action_or_object_overlap_cannot_consume_the_whole_card(instruction):
    assert matches_reported(instruction, reported("cleaned the contacts and filter")) is None


@pytest.mark.parametrize("extra", [{"polarity": "negated"}, {"polarity": "uncertain"}, {"status": "superseded"},
                                    {"source_kind": "model"}, {"source": "assistant"}])
def test_only_active_affirmed_user_reports_can_cover_actions(extra):
    assert not reported("cleaned the contacts", **extra)


@pytest.mark.parametrize("instruction,value", [
    ("Clean the contacts.", "cleaned the electrical connections"),
    ("Replace the filter.", "replaced the filters"),
    ("Wipe the brushes and filter.", "wiped the brushes and filters"),
    ("Clean and replace the filter.", "cleaned and replaced the filter"),
])
def test_explicit_complete_operations_still_deduplicate(instruction, value):
    assert matches_reported(instruction, reported(value)) == value


def test_other_issues_reports_do_not_cover_current_operation():
    state = {"active_issue_id": "new", "issues": {"new": {"facts": []}, "old": {"facts": [
        {"kind": "action_taken", "status": "active", "value": "cleaned contacts"},
    ]}}}
    assert not user_reported_actions(state)
