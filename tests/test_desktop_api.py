import importlib
import io
import json

import pandas as pd

from src.parsers.base import create_empty_uul


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


def _write_processed_fixture(api_module, rows):
    df = create_empty_uul()
    for row in rows:
        df.loc[len(df)] = {
            "source_platform": row.get("source_platform", "alipay"),
            "user_id": row.get("user_id", "我"),
            "transaction_id": row["transaction_id"],
            "timestamp": row.get("timestamp", "2026-01-01 10:00:00"),
            "direction": row.get("direction", "支出"),
            "amount": row.get("amount", 10.0),
            "counterparty": row.get("counterparty", "商户"),
            "description": row.get("description", "商品"),
            "payment_method": "",
            "status": "交易成功",
            "platform_category": "",
            "platform_tx_type": "",
            "original_tx_id": "",
            "merchant_order_id": "",
            "note": "",
            "track": row.get("track", "consumption"),
            "is_refunded": False,
            "refund_amount": 0.0,
            "effective_amount": row.get("effective_amount", row.get("amount", 10.0)),
            "is_ignored": False,
            "global_category_l1": row.get("global_category_l1", ""),
            "global_category_l2": row.get("global_category_l2", ""),
        }
    api_module.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(api_module.OUTPUT_DIR / "processed_data.csv", index=False, encoding="utf-8-sig")


def test_apply_existing_tagging_results_updates_dashboard_data(tmp_path, monkeypatch):
    client, api_module = make_client(tmp_path, monkeypatch)
    _write_processed_fixture(api_module, [{"transaction_id": "tx-1"}])

    batch_dir = api_module.OUTPUT_DIR / "tagging_batches"
    batch_dir.mkdir(parents=True)
    (batch_dir / "manifest.json").write_text(
        json.dumps([{"file": str(batch_dir / "batch_000.txt"), "indices": [0], "count": 1}]),
        encoding="utf-8",
    )
    (batch_dir / "batch_000_result.json").write_text(
        json.dumps([{"index": 1, "l1": "餐饮美食", "l2": "堂食正餐"}], ensure_ascii=False),
        encoding="utf-8",
    )

    response = client.post("/api/tagging/apply")
    tx = client.get("/api/transactions").get_json()["records"][0]

    assert response.status_code == 200
    assert response.get_json()["applied_records"] == 1
    assert tx["category_l1"] == "餐饮美食"
    assert tx["category_l2"] == "堂食正餐"


def test_tagging_status_reports_batches_and_task_history(tmp_path, monkeypatch):
    client, api_module = make_client(tmp_path, monkeypatch)
    _write_processed_fixture(api_module, [{"transaction_id": "tx-1"}])

    batch_dir = api_module.OUTPUT_DIR / "tagging_batches"
    batch_dir.mkdir(parents=True)
    (batch_dir / "batch_000.txt").write_text("prompt", encoding="utf-8")
    (batch_dir / "batch_001.txt").write_text("prompt", encoding="utf-8")
    (batch_dir / "batch_000_result.json").write_text("[]", encoding="utf-8")
    (api_module.OUTPUT_DIR / "tagging_tasks.json").write_text(
        json.dumps([{"id": "task-1", "status": "completed", "completed_batches": 1, "total_batches": 2}]),
        encoding="utf-8",
    )

    response = client.get("/api/tagging/status")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["batches"]["total"] == 2
    assert payload["batches"]["completed"] == 1
    assert payload["batches"]["pending"] == 1
    assert payload["tasks"][0]["id"] == "task-1"


def test_process_response_separates_total_rows_from_pending_tagging_records(tmp_path, monkeypatch):
    client, api_module = make_client(tmp_path, monkeypatch)
    df = create_empty_uul()
    df.loc[len(df)] = {
        "source_platform": "alipay",
        "user_id": "我",
        "transaction_id": "consume-1",
        "timestamp": "2026-01-01 10:00:00",
        "direction": "支出",
        "amount": 10.0,
        "counterparty": "餐厅",
        "description": "午餐",
        "payment_method": "",
        "status": "交易成功",
        "platform_category": "",
        "platform_tx_type": "",
        "original_tx_id": "",
        "merchant_order_id": "",
        "note": "",
        "track": "consumption",
        "is_refunded": False,
        "refund_amount": 0.0,
        "effective_amount": 10.0,
        "is_ignored": False,
        "global_category_l1": "",
        "global_category_l2": "",
    }
    df.loc[len(df)] = {
        **df.iloc[0].to_dict(),
        "transaction_id": "cash-1",
        "track": "cashflow",
        "counterparty": "银行",
    }

    def fake_pipeline(_data_dir, output_dir):
        api_module.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(api_module.OUTPUT_DIR / "processed_data.csv", index=False, encoding="utf-8-sig")
        return df

    monkeypatch.setattr(api_module, "run_pipeline", fake_pipeline)

    response = client.post("/api/process")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total_records"] == 2
    assert payload["consumption_records"] == 1
    assert payload["pending_tagging_records"] == 1


def test_model_profiles_can_be_saved_and_switched_without_exposing_keys(tmp_path, monkeypatch):
    client, api_module = make_client(tmp_path, monkeypatch)

    first = client.post(
        "/api/model-profiles",
        json={
            "name": "Mimo",
            "api_key": "sk-mimo-secret",
            "base_url": "https://mimo.example/anthropic",
            "model": "mimo-model",
            "make_active": True,
        },
    )
    second = client.post(
        "/api/model-profiles",
        json={
            "name": "Backup",
            "api_key": "sk-backup-secret",
            "base_url": "https://backup.example/anthropic",
            "model": "backup-model",
            "make_active": False,
        },
    )
    second_id = second.get_json()["profile"]["id"]
    switched = client.post("/api/model-profiles/active", json={"id": second_id})
    profiles = client.get("/api/model-profiles")
    config = client.get("/api/config")

    assert first.status_code == 200
    assert second.status_code == 200
    assert switched.status_code == 200
    assert profiles.get_json()["active_id"] == second_id
    assert "sk-backup-secret" not in profiles.get_data(as_text=True)
    assert config.get_json()["base_url"] == "https://backup.example/anthropic"
    assert config.get_json()["model"] == "backup-model"
    assert "sk-backup-secret" in api_module.CONFIG_PATH.read_text(encoding="utf-8")
