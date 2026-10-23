from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lifegather.main import create_app

pytestmark = pytest.mark.usefixtures("configured_database")


@pytest.mark.parametrize("data_subdirectory", [".", "private"])
def test_rejects_private_data_inside_static_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data_subdirectory: str
) -> None:
    monkeypatch.setenv("LIFEGATHER_STATIC_DIR", str(tmp_path))
    monkeypatch.setenv("LIFEGATHER_DATA_DIR", str(tmp_path / data_subdirectory))

    with pytest.raises(ValueError, match="outside the static directory"):
        create_app()


def test_serves_frontend_without_shadowing_health(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<h1>LifeGather</h1>", encoding="utf-8")
    (static_dir / "app.js").write_text("console.log('ready')", encoding="utf-8")
    monkeypatch.setenv("LIFEGATHER_STATIC_DIR", str(static_dir))

    with TestClient(create_app()) as client:
        assert client.get("/").text == "<h1>LifeGather</h1>"
        assert client.get("/app.js").text == "console.log('ready')"
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/missing.js").status_code == 404


def test_creates_private_data_directory_outside_web_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("LifeGather", encoding="utf-8")
    monkeypatch.setenv("LIFEGATHER_DATA_DIR", str(data_dir))
    monkeypatch.setenv("LIFEGATHER_STATIC_DIR", str(static_dir))

    with TestClient(create_app()) as client:
        assert data_dir.is_dir()
        (data_dir / "private.txt").write_text("private fixture", encoding="utf-8")
        assert client.get("/private.txt").status_code == 404
        assert client.get("/data/private.txt").status_code == 404

    assert (data_dir / "private.txt").read_text(encoding="utf-8") == "private fixture"


def test_static_cache_policy_revalidates_html_and_only_pins_hashed_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    static_dir = tmp_path / "static"
    (static_dir / "assets").mkdir(parents=True)
    for filename in (
        "index.html",
        "app.js",
        "assets/index-AbC123xy.js",
        "assets/page-AbC123xy.html",
    ):
        (static_dir / filename).write_text("synthetic static content", encoding="utf-8")
    monkeypatch.setenv("LIFEGATHER_STATIC_DIR", str(static_dir))
    with TestClient(create_app()) as client:
        for path in (
            "/",
            "/index.html",
            "/app.js",
            "/missing.js",
            "/assets/missing-AbC123xy.js",
            "/assets/page-AbC123xy.html",
        ):
            assert (
                client.get(path).headers["cache-control"] == "no-cache, must-revalidate"
            )
        html = client.get("/")
        unchanged = client.get("/", headers={"If-None-Match": html.headers["etag"]})
        assert unchanged.status_code == 304
        assert unchanged.headers["cache-control"] == "no-cache, must-revalidate"
        asset = client.get("/assets/index-AbC123xy.js")
        assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
        html_asset = client.get("/assets/page-AbC123xy.html")
        assert (
            client.get(
                "/assets/page-AbC123xy.html",
                headers={"If-None-Match": html_asset.headers["etag"]},
            ).headers["cache-control"]
            == "no-cache, must-revalidate"
        )
        assert client.get("/api/version").headers["cache-control"] == "no-store"
