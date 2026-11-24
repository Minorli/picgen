from __future__ import annotations

import pytest


@pytest.fixture()
def history_client(make_client, settings_factory):
    client, _, _ = make_client(settings=settings_factory(auth_enabled=True))
    response = client.post("/api/auth/register", json={"username": "alice", "password": "secure test password"})
    assert response.status_code == 200
    return client, client.app.state.auth_store, response.json()["user"]["id"]


def _job(store, user_id):
    return store.create_generation_job(request_id="page-test", user_id=user_id, endpoint_path="/api/generate")


def test_job_pages_are_complete_stable_and_private(history_client):
    client, store, user_id = history_client
    other = store.create_user("bob", "secure test password")
    expected_ids = []
    for _ in range(5):
        expected_ids.append(_job(store, user_id))
        _job(store, other.id)
    first = client.get("/api/jobs?limit=2").json()
    assert first["scope"] == "self"
    assert first["count"] == 2
    assert [job["id"] for job in first["jobs"]] == expected_ids[-2:][::-1]
    assert first["next_before_id"] == first["jobs"][-1]["id"]
    new_job = _job(store, user_id)
    seen_ids = [job["id"] for job in first["jobs"]]
    cursor = first["next_before_id"]
    while cursor is not None:
        response = client.get("/api/jobs", params={"limit": 2, "before_id": cursor})
        assert response.status_code == 200
        page = response.json()
        assert page["count"] == len(page["jobs"])
        assert all(job["user_id"] == user_id for job in page["jobs"])
        seen_ids.extend(job["id"] for job in page["jobs"])
        cursor = page["next_before_id"]
    assert seen_ids == expected_ids[::-1]
    assert new_job not in seen_ids
    assert client.get("/api/jobs?limit=1").json()["jobs"][0]["id"] == new_job


def test_job_pagination_handles_maximum_page_and_exact_end(history_client):
    client, store, user_id = history_client
    job_ids = [_job(store, user_id) for _ in range(101)]
    page = client.get("/api/jobs?limit=100").json()
    assert page["count"] == 100
    assert page["next_before_id"] == job_ids[1]
    last = client.get("/api/jobs", params={"limit": 1, "before_id": page["next_before_id"]}).json()
    assert [job["id"] for job in last["jobs"]] == job_ids[:1]
    assert last["next_before_id"] is None


@pytest.mark.parametrize("query", [
    "before_id=0", "before_id=-1", "before_id=invalid", "before_id=1.5",
    "before_id=9223372036854775808", "limit=0", "limit=101",
])
def test_invalid_job_cursor_or_limit_rejected(history_client, query):
    client, _, _ = history_client
    assert client.get(f"/api/jobs?{query}").status_code == 422


def test_empty_history_has_no_next_cursor(history_client):
    client, _, _ = history_client
    assert client.get("/api/jobs").json() == {
        "scope": "self", "count": 0, "jobs": [], "next_before_id": None,
    }
