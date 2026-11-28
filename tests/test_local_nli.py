import pytest

from local_nli import nli_scores


def test_nli_label_mapping_not_assumed_order():
    labels = {"0": "contradiction", "1": "entailment", "2": "neutral"}
    r = nli_scores([[0, 10, 1]], labels)
    assert r["label"] == "entailment"
    assert not r["calibrated"] and r["authority"] == "none"
    assert nli_scores([[100, 110, 101]], labels) == r
    assert nli_scores([[0, 0, 0]], labels)["label"] is None


@pytest.mark.parametrize("logits", [[[0, 1]], [[float("nan"), 0, 0]], [[True, 0, 0]]])
def test_invalid_logits(logits):
    with pytest.raises(ValueError):
        nli_scores(logits, {"0": "entailment", "1": "neutral", "2": "contradiction"})


def test_unknown_label_mapping_rejected():
    with pytest.raises(ValueError):
        nli_scores([[0, 1, 0]], {"0": "LABEL_0", "1": "neutral", "2": "contradiction"})
