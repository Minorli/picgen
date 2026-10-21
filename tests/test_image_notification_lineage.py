from __future__ import annotations

from picgen.auth import AuthStore


def test_image_detail_keeps_original_job_facts_after_final_asset_replacement(tmp_path):
    store = AuthStore(tmp_path / "auth.sqlite3")
    owner = store.create_user("alice", "secure test password")
    other = store.create_user("bob", "secure test password")
    job_id = store.create_generation_job(
        request_id="original-generation-request",
        user_id=owner.id,
        endpoint_path="/api/generate",
        size="1088x2240",
        sample_count=3,
    )
    images = store.complete_generation_job(
        job_id=job_id,
        result={"images": [
            {"saved_image_url": "files/outputs/original-1.png", "saved_image_width": 1088, "saved_image_height": 2240},
            {"saved_image_url": "files/outputs/original-2.png", "saved_image_width": 1088, "saved_image_height": 2240},
        ]},
        elapsed_ms=132720.1,
    )
    image_id = images[0]["id"]
    store.replace_generated_image_asset(
        generated_image_id=image_id,
        user_id=owner.id,
        image={
            "saved_image_url": "files/outputs/final.png",
            "saved_image_width": 544,
            "saved_image_height": 1120,
            "metadata": {"image_model": "recorded-image-model"},
        },
        logo_overlay_applied=True,
    )

    detail = store.generated_image_detail_for_user(generated_image_id=image_id, user_id=owner.id)

    assert detail is not None
    assert detail["job_id"] == job_id
    assert detail["saved_image_width"] == 544
    assert detail["saved_image_height"] == 1120
    assert detail["metadata"]["image_model"] == "recorded-image-model"
    assert detail["lineage"]["size"] == "1088x2240"
    assert detail["lineage"]["image_count"] == 2
    assert detail["lineage"]["sample_count"] == 3
    assert detail["lineage"]["elapsed_ms"] == 132720.1
    assert detail["lineage"]["request_id"] == "original-generation-request"
    assert detail["lineage"]["endpoint_path"] == "/api/generate"
    assert store.generated_image_detail_for_user(generated_image_id=image_id, user_id=other.id) is None
