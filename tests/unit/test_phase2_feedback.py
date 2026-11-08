import pytest

from maat.db import connect
from maat.feedback.collector import FeedbackCollector, FeedbackRejected
from maat.feedback.signals import FeedbackIn, derive_claim, edit_diff
from maat.proposal.cluster import cluster_events
from maat.repo import Repo
from maat.settings import Settings


@pytest.fixture
def repo() -> Repo:
    r = Repo(connect())
    r.log_task(
        "t1",
        "u1",
        "clause_query",
        "What is the min_cover_mm of cover:severe?",
        "The min_cover_mm of cover:severe is 25.",
        {},
        1,
        1.0,
    )
    return r


def test_agent_origin_rejected_and_audited(repo) -> None:
    col = FeedbackCollector(repo, Settings())
    with pytest.raises(FeedbackRejected) as e:
        col.ingest(FeedbackIn(user_id="u1", signal_type="comment", text="x", origin="agent"))
    assert e.value.code == "agent_origin"
    assert repo.list_feedback() == [] and repo.list_audit("feedback.rejected")


def test_rate_limit(repo) -> None:
    col = FeedbackCollector(repo, Settings(user_rate_limit_per_hour=2))
    for _ in range(2):
        col.ingest(FeedbackIn(user_id="u1", signal_type="accept", task_id="t1"))
    with pytest.raises(FeedbackRejected) as e:
        col.ingest(FeedbackIn(user_id="u1", signal_type="accept", task_id="t1"))
    assert e.value.code == "rate_limited"


def test_edit_derives_claim_diff_and_monitors(repo) -> None:
    col = FeedbackCollector(repo, Settings())
    eid = col.ingest(
        FeedbackIn(
            user_id="u1",
            signal_type="edit",
            task_id="t1",
            edit="The min_cover_mm of cover:severe is 47.",
        )
    )
    ev = next(e for e in repo.list_feedback() if e["event_id"] == eid)
    assert ev["claim_json"] == {
        "subject": "cover:severe",
        "attribute": "min_cover_mm",
        "value": 47.0,
    }
    assert "-The min_cover_mm" in ev["edit_diff"] and ev["edit_text"].endswith("47.")
    col.ingest(FeedbackIn(user_id="u1", signal_type="redo", task_id="t1"))
    col.ingest(FeedbackIn(user_id="u1", signal_type="rating", task_id="t1", rating=1))
    w = repo.get_monitor_window(1)
    assert (w["edits"], w["redos"], w["n"]) == (1, 2, 3)


def test_validation_errors(repo) -> None:
    col = FeedbackCollector(repo, Settings())
    with pytest.raises(FeedbackRejected):
        col.ingest(FeedbackIn(user_id="u1", signal_type="edit", task_id="t1"))
    with pytest.raises(FeedbackRejected):
        col.ingest(FeedbackIn(user_id="u1", signal_type="accept", task_id="nope"))


def test_derive_claim_cases() -> None:
    q = "What is the severity of incident:fall_from_height?"
    assert derive_claim("incident_triage", q, "It is critical.")["value"] == "critical"
    assert (
        derive_claim("clause_query", "What is the max_deg of ladder:angle?", "74 deg")["value"]
        == 74.0
    )
    assert derive_claim("unit_calc", "COMPUTE: 1+1", "2") is None
    assert edit_diff("a", "a") == ""


def _events(repo, specs):
    for i, (user, subj, text) in enumerate(specs):
        repo.log_feedback(
            f"e{i}",
            user,
            "comment",
            text=text,
            claim={"subject": subj, "attribute": "a", "value": i} if subj else None,
        )
    return repo.list_feedback()


def test_clustering_by_subject_and_user_cap(repo) -> None:
    ev = _events(
        repo,
        [("u1", "cover:severe", "x")] * 3
        + [("u2", "cover:severe", "x"), ("u1", "cover:mild", "y")],
    )
    clusters = cluster_events(ev, {}, Settings(cluster_user_cap=2))
    by_key = {c.key: c for c in clusters}
    c = by_key["clause_query|cover:severe"]
    assert len(c.event_ids) == 4 and len(c.counted_event_ids) == 3  # u1 capped at 2
    assert c.users == {"u1", "u2"} and "clause_query|cover:mild" in by_key


def test_clustering_merges_near_duplicate_text(repo) -> None:
    ev = _events(
        repo,
        [
            ("u1", None, "scaffold guardrail height is wrong please fix"),
            ("u2", None, "scaffold guardrail height wrong fix please"),
            ("u3", None, "tender deadline format unclear"),
        ],
    )
    texts = cluster_events(ev, {}, Settings(cluster_sim_threshold=0.6))
    sizes = sorted(len(c.event_ids) for c in texts)
    assert sizes == [1, 2]
