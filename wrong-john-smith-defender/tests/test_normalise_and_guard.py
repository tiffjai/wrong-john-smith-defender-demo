import pytest

from defender.guard import dob_check
from defender.normalise import parse_dob


@pytest.mark.parametrize("raw,precision,value", [
    ("1980-03-14", "full", "1980-03-14"), ("02 Nov 1974", "full", "1974-11-02"),
    ("30/09/1991", "full", "1991-09-30"), ("Jul 1988", "year_month", "1988-07"),
    ("1988-07", "year_month", "1988-07"), ("1988", "year", "1988"),
    (None, "unknown", None), ("", "unknown", None),
    ("31/02/1990", "unparseable", None), ("sometime in 1990", "unparseable", None),
])
def test_parse_dob_precision(raw, precision, value):
    d = parse_dob(raw)
    assert d["precision"] == precision and d["value"] == value


def rec(rid, raw, status):
    return {"record_id": rid, "derived": {"dob": parse_dob(raw)},
            "dob": {"raw": raw, "verification": {"status": status}}}


def test_verified_full_different_is_contradiction():
    assert dob_check(rec("a", "1980-03-14", "verified"), rec("b", "1974-11-02", "verified"))["status"] == "contradiction"


def test_verified_full_same_is_consistent():
    assert dob_check(rec("a", "1980-03-14", "verified"), rec("b", "14/03/1980", "verified"))["status"] == "consistent"


@pytest.mark.parametrize("a,b", [
    (("1980-03-14", "verified"), ("1980-04", "verified")),      # partial precision, even though verified
    (("1980-03-14", "verified"), ("1975", "verified")),          # year only, different year
    (("1980-03-14", "verified"), ("1974-11-02", "unverified")),  # unverified full date
    (("1980-03-14", "unverified"), ("1974-11-02", "unverified")),
    (("1980-03-14", "verified"), (None, "unknown")),             # unknown stays unknown
    (("1980-03-14", "verified"), ("31/02/1990", "verified")),    # unparseable treated as unknown
])
def test_not_a_contradiction(a, b):
    chk = dob_check(rec("a", *a), rec("b", *b))
    assert chk["status"] == "not_assessable", chk
    assert chk["reasons"]
