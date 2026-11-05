from __future__ import annotations

import pytest


@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_entry_page_revalidates_even_for_conditional_requests(make_client, settings_factory, path):
    settings = settings_factory()
    (settings.static_dir / "index.html").write_text('<script src="app.js?v=new"></script>')
    client, _, _ = make_client(settings=settings)
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    cached = client.get(path, headers={"If-None-Match": response.headers["etag"]})
    assert cached.status_code == 304
    assert cached.headers["cache-control"] == "no-cache"


def test_entry_page_rule_preserves_api_and_versioned_asset_cache_policies(make_client, settings_factory):
    settings = settings_factory()
    (settings.static_dir / "app.js").write_text("// versioned asset")
    client, _, _ = make_client(settings=settings)
    response = client.get("/app.js?v=new")
    assert response.status_code == 200
    assert response.headers.get("cache-control") not in {"no-cache", "no-store"}
    assert client.get("/api/config").headers["cache-control"] == "no-store"
