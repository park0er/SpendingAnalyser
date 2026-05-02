import importlib
import io


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.env"))

    import src.api as api_module

    api_module = importlib.reload(api_module)
    api_module.app.config.update(TESTING=True)
    return api_module.app.test_client(), api_module


def test_empty_first_launch_returns_safe_meta_and_summary(tmp_path, monkeypatch):
    client, _api_module = make_client(tmp_path, monkeypatch)

    meta = client.get("/api/meta")
    summary = client.get("/api/summary")

    assert meta.status_code == 200
    assert summary.status_code == 200
    assert meta.get_json()["users"] == []
    assert summary.get_json()["total_records"] == 0
    assert summary.get_json()["total_spend"] == 0


def test_model_config_can_be_saved_and_read_without_exposing_key(tmp_path, monkeypatch):
    client, api_module = make_client(tmp_path, monkeypatch)

    saved = client.post(
        "/api/config",
        json={
            "api_key": "sk-test-secret",
            "base_url": "https://example.test/anthropic",
            "model": "example-model",
        },
    )
    loaded = client.get("/api/config")

    assert saved.status_code == 200
    assert loaded.status_code == 200
    assert loaded.get_json() == {
        "api_key_configured": True,
        "base_url": "https://example.test/anthropic",
        "model": "example-model",
    }
    assert "sk-test-secret" in api_module.CONFIG_PATH.read_text(encoding="utf-8")
    assert "sk-test-secret" not in loaded.get_data(as_text=True)


def test_upload_stores_files_under_selected_platform_name(tmp_path, monkeypatch):
    client, api_module = make_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/uploads",
        data={
            "platform": "alipay",
            "user": "我",
            "files": (io.BytesIO(b"csv-content"), "january.csv"),
        },
        content_type="multipart/form-data",
    )
    listed = client.get("/api/uploads")

    assert response.status_code == 200
    uploaded = response.get_json()["files"][0]
    assert uploaded["platform"] == "alipay"
    assert uploaded["user"] == "我"
    assert uploaded["name"].startswith("支付宝")
    assert (api_module.DATA_DIR / "我" / uploaded["name"]).read_bytes() == b"csv-content"
    assert listed.get_json()["files"][0]["name"] == uploaded["name"]
    assert listed.get_json()["files"][0]["user"] == "我"


def test_upload_preserves_existing_chinese_platform_prefix(tmp_path, monkeypatch):
    client, _api_module = make_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/uploads",
        data={
            "platform": "alipay",
            "user": "老婆",
            "files": (
                io.BytesIO(b"csv-content"),
                "支付宝交易明细(20250101-20251231).csv",
            ),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    uploaded = response.get_json()["files"][0]
    assert uploaded["name"] == "支付宝交易明细(20250101-20251231).csv"
    assert uploaded["platform"] == "alipay"
    assert uploaded["user"] == "老婆"


def test_upload_requires_user_name(tmp_path, monkeypatch):
    client, _api_module = make_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/uploads",
        data={
            "platform": "alipay",
            "user": "",
            "files": (io.BytesIO(b"csv-content"), "january.csv"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert "用户" in response.get_json()["error"]


def test_uploaded_users_are_available_before_processing(tmp_path, monkeypatch):
    client, _api_module = make_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/uploads",
        data={
            "platform": "jd",
            "user": "老婆",
            "files": (io.BytesIO(b"csv-content"), "orders.csv"),
        },
        content_type="multipart/form-data",
    )
    meta = client.get("/api/meta")

    assert response.status_code == 200
    assert meta.status_code == 200
    assert meta.get_json()["users"] == [{"id": "老婆", "label": "老婆"}]
