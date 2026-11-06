"""Type hints must match whole words without discarding Indic letters or marks."""

import pytest

from memora.services.document_type import classify, normalise, should_refuse


@pytest.mark.parametrize(
    ('hint', 'expected'),
    [
        ('आधार', 'aadhaar'),
        ('गुणपत्रिका', 'marksheet'),
        ('वीज बिल', 'bill'),
        ('पॅन', 'pan'),
        ('माझे प्रमाणपत्र', 'certificate'),
        ('admit_card', 'admit_card'),
        ('e-ticket', 'ticket'),
        ('PAN card', 'pan'),
        ('fee receipt', 'receipt'),
        ('receipts', 'receipt'),
    ],
)
def test_multilingual_and_canonical_hints(hint, expected):
    assert normalise(hint) == expected


@pytest.mark.parametrize('hint', ['res', 'port', 'taxi', 'character', 'panorama', 'आधारित'])
def test_substrings_cannot_invent_a_document_type(hint):
    assert normalise(hint) is None
    assert should_refuse(hint, set()) is False


def test_hyphenated_alias_is_normalized_on_both_sides():
    assert classify(text='Your e-ticket for the train') == 'ticket'
