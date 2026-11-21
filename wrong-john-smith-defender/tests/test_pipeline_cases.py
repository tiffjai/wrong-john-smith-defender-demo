import math

import pytest

from defender.pipeline import candidate_pairs, run_pipeline


def pair(result, l, r):
    return result["pairs_by_id"][f"{l}|{r}"]


def test_same_candidate_pairs_for_all_three_methods(result):
    n = 0
    for p in result["pairs"]:
        assert all(k in p for k in ("name_only", "splink", "guarded"))
        assert p["name_only"]["decision"] and p["splink"]["decision"] and p["guarded"]["decision"]
        n += 1
    assert n == 5
    assert {p["pair_id"] for p in result["pairs"]} == {
        "SYN-01-A|SYN-01-B", "SYN-03-A|SYN-03-B", "SYN-08-A|SYN-08-B", "SYN-08-A|SYN-08-C", "SYN-08-B|SYN-08-C"}


def test_splink_recomputation_and_levels_match_config(result):
    for p in result["pairs"]:
        s = p["splink"]
        assert math.isclose(s["match_probability"], s["recomputed_probability"], rel_tol=1e-9)
        for c in s["contributions"]:
            if c["level_key"] == "null":
                assert c["bayes_factor"] == 1.0
            else:
                assert math.isclose(c["bayes_factor"], c["m_probability"] / c["u_probability"], rel_tol=1e-9)


def test_case01_goes_to_analyst_review(result):
    p = pair(result, "SYN-01-A", "SYN-01-B")
    assert p["name_only"]["decision"] == "LINK" and p["splink"]["decision"] == "LINK"
    assert p["guarded"]["decision"] == "REVIEW"
    assert p["guarded"]["outcome"] == "ROUTED_TO_REVIEW_DIRECT_CONTRADICTION"
    assert p["guarded"]["dob_check"]["status"] == "contradiction"
    assert result["cases"]["CASE-01"]["routes"]["splink_guard"] == "ANALYST_REVIEW"


def test_case03_alias_candidate_stays_visible(result):
    p = pair(result, "SYN-03-A", "SYN-03-B")
    assert p["blocking_rules"] == ["same_alias_group"]            # found ONLY through the alias table
    assert p["splink"]["contributions"][0]["level_key"] == "alias"
    assert p["name_only"]["decision"] == "NO_LINK"                  # name-only cannot see the alias
    assert p["splink"]["decision"] == "LINK" and p["guarded"]["decision"] == "LINK"
    assert p["guarded"]["dob_check"]["status"] == "not_assessable"  # partial + unverified: not a contradiction
    assert p["guarded"]["outcome"] == "PASS_NO_CONTRADICTION"
    assert result["cases"]["CASE-03"]["routes"]["splink_guard"] == "CANDIDATE_VISIBLE"
    assert result["alias"]["groups"]["ALIAS-0001"]["source_id"] == "SRC-SYN-ALIAS-001"


def test_case03_without_alias_table_is_not_even_a_candidate():
    r = run_pipeline(use_alias=False)
    assert "SYN-03-A|SYN-03-B" not in r["pairs_by_id"]


def test_case08_chain_goes_to_analyst_review(result):
    ab, bc, ac = (pair(result, "SYN-08-A", "SYN-08-B"), pair(result, "SYN-08-B", "SYN-08-C"),
                  pair(result, "SYN-08-A", "SYN-08-C"))
    assert ab["splink"]["decision"] == "LINK" and bc["splink"]["decision"] == "LINK"
    assert ac["splink"]["decision"] == "NO_LINK"
    # the pairwise B DOB is unknown: never treated as a mismatch
    for p in (ab, bc):
        assert p["guarded"]["dob_check"]["status"] == "not_assessable"
        assert [c for c in p["splink"]["contributions"] if c["field"] == "dob"][0]["level_key"] == "null"
    assert ac["guarded"]["dob_check"]["status"] == "contradiction"
    assert ac["guarded"]["outcome"] == "ROUTED_TO_REVIEW_DIRECT_CONTRADICTION"
    assert ab["guarded"]["outcome"] == bc["guarded"]["outcome"] == "ROUTED_TO_REVIEW_CHAIN_CONTRADICTION"
    assert all(pair_["guarded"]["decision"] == "REVIEW" for pair_ in (ab, bc, ac))
    assert result["cases"]["CASE-08"]["routes"]["splink_guard"] == "ANALYST_REVIEW"


def test_guard_never_hides_pairs(result):
    for p in result["pairs"]:
        if p["splink"]["decision"] in ("LINK", "REVIEW"):
            assert p["guarded"]["decision"] in ("LINK", "REVIEW")
        if p["splink"]["decision"] == "NO_LINK" and not p["guarded"]["changed_by_guard"]:
            assert p["guarded"]["decision"] == "NO_LINK"


def test_candidate_generator_matches_splink_blocking(result):
    gen = candidate_pairs(result["records"], result["config"]["parameters"]["splink"]["blocking_rules"])
    assert {p["pair_id"] for p in gen} == set(result["pairs_by_id"])
