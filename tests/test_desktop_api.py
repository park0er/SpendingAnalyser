import importlib
import io
import json
import sys
import time
import types

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


def test_dashboard_reads_do_not_process_uploaded_bills(tmp_path, monkeypatch):
    client, api_module = make_client(tmp_path, monkeypatch)

    def fail_pipeline(*_args, **_kwargs):
        raise AssertionError("dashboard API must not start processing")

    monkeypatch.setattr(api_module, "run_pipeline", fail_pipeline)
    uploaded = api_module.DATA_DIR / "我" / "支付宝_bill.csv"
    uploaded.parent.mkdir(parents=True)
    uploaded.write_text("raw", encoding="utf-8")

    summary = client.get("/api/summary")
    meta = client.get("/api/meta")

    assert summary.status_code == 200
    assert summary.get_json()["total_records"] == 0
    assert meta.get_json()["users"] == [{"id": "我", "label": "我"}]
    assert not (api_module.OUTPUT_DIR / "processed_data.csv").exists()


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


def test_uploaded_file_can_be_deleted(tmp_path, monkeypatch):
    client, api_module = make_client(tmp_path, monkeypatch)
    uploaded = client.post(
        "/api/uploads",
        data={
            "platform": "alipay",
            "user": "我",
            "files": (io.BytesIO(b"csv-content"), "january.csv"),
        },
        content_type="multipart/form-data",
    ).get_json()["files"][0]

    response = client.delete(f"/api/uploads/{uploaded['relative_path']}")
    listed = client.get("/api/uploads").get_json()["files"]

    assert response.status_code == 200
    assert response.get_json()["deleted"] is True
    assert listed == []
    assert not (api_module.DATA_DIR / uploaded["relative_path"]).exists()


def test_uploaded_file_can_be_moved_to_another_user_and_platform(tmp_path, monkeypatch):
    client, api_module = make_client(tmp_path, monkeypatch)
    uploaded = client.post(
        "/api/uploads",
        data={
            "platform": "alipay",
            "user": "我",
            "files": (io.BytesIO(b"csv-content"), "january.csv"),
        },
        content_type="multipart/form-data",
    ).get_json()["files"][0]

    response = client.patch(
        f"/api/uploads/{uploaded['relative_path']}",
        json={"platform": "wechat", "user": "老婆"},
    )
    listed = client.get("/api/uploads").get_json()["files"]

    assert response.status_code == 200
    updated = response.get_json()["file"]
    assert updated["platform"] == "wechat"
    assert updated["user"] == "老婆"
    assert updated["name"].startswith("微信")
    assert updated["relative_path"].startswith("老婆/")
    assert (api_module.DATA_DIR / updated["relative_path"]).read_bytes() == b"csv-content"
    assert not (api_module.DATA_DIR / uploaded["relative_path"]).exists()
    assert listed == [updated]


def test_new_upload_clears_current_workspace_but_keeps_processed_versions(tmp_path, monkeypatch):
    client, api_module = make_client(tmp_path, monkeypatch)
    version_dir = api_module.OUTPUT_DIR / "processed_versions" / "version-old"
    version_dir.mkdir(parents=True)
    (version_dir / "processed_data.csv").write_text("snapshot", encoding="utf-8")
    (api_module.OUTPUT_DIR / "processed_versions.json").write_text(
        json.dumps({"active_id": "version-old", "versions": [{"id": "version-old", "name": "旧版本"}]}),
        encoding="utf-8",
    )
    (api_module.OUTPUT_DIR / "processed_data.csv").write_text("current", encoding="utf-8")
    (api_module.OUTPUT_DIR / "tagging_tasks.json").write_text("[]", encoding="utf-8")
    batch_dir = api_module.OUTPUT_DIR / "tagging_batches"
    batch_dir.mkdir(parents=True)
    (batch_dir / "batch_000.txt").write_text("old prompt", encoding="utf-8")
    old_file = api_module.DATA_DIR / "我" / "支付宝_old.csv"
    old_file.parent.mkdir(parents=True)
    old_file.write_text("old", encoding="utf-8")

    response = client.post(
        "/api/uploads",
        data={
            "platform": "wechat",
            "user": "老婆",
            "files": (io.BytesIO(b"new"), "new.xlsx"),
        },
        content_type="multipart/form-data",
    )

    uploaded = response.get_json()["files"][0]
    assert response.status_code == 200
    assert uploaded["relative_path"].startswith("老婆/")
    assert not old_file.exists()
    assert not (api_module.OUTPUT_DIR / "processed_data.csv").exists()
    assert not (api_module.OUTPUT_DIR / "tagging_tasks.json").exists()
    assert not batch_dir.exists()
    versions = json.loads((api_module.OUTPUT_DIR / "processed_versions.json").read_text(encoding="utf-8"))
    assert versions["active_id"] == ""
    assert versions["versions"][0]["id"] == "version-old"
    assert (version_dir / "processed_data.csv").read_text(encoding="utf-8") == "snapshot"


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


def test_process_creates_processed_data_version_and_can_switch_versions(tmp_path, monkeypatch):
    client, api_module = make_client(tmp_path, monkeypatch)
    first = create_empty_uul()
    first.loc[len(first)] = {
        "source_platform": "alipay",
        "user_id": "我",
        "transaction_id": "tx-first",
        "timestamp": "2026-01-01 10:00:00",
        "direction": "支出",
        "amount": 10.0,
        "counterparty": "商户A",
        "description": "商品",
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
    second = first.copy()
    second.at[0, "transaction_id"] = "tx-second"
    second.at[0, "counterparty"] = "商户B"
    frames = [first, second]

    def fake_pipeline(_data_dir, output_dir):
        df = frames.pop(0)
        api_module.Path(output_dir).mkdir(parents=True, exist_ok=True)
        df.to_csv(api_module.OUTPUT_DIR / "processed_data.csv", index=False, encoding="utf-8-sig")
        return df

    monkeypatch.setattr(api_module, "run_pipeline", fake_pipeline)

    first_response = client.post("/api/process")
    first_version = first_response.get_json()["processed_version"]["id"]
    second_response = client.post("/api/process")
    second_version = second_response.get_json()["processed_version"]["id"]
    versions = client.get("/api/processed-versions").get_json()
    switch_response = client.post("/api/processed-versions/active", json={"id": first_version})
    tx = client.get("/api/transactions").get_json()["records"][0]

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_version != second_version
    assert versions["active_id"] == second_version
    assert [v["id"] for v in versions["versions"]] == [second_version, first_version]
    assert switch_response.status_code == 200
    assert tx["id"] == "tx-first"


def test_manual_category_update_requires_processed_version_when_versions_exist(tmp_path, monkeypatch):
    client, api_module = make_client(tmp_path, monkeypatch)
    _write_processed_fixture(api_module, [{"transaction_id": "tx-1"}])
    api_module._save_processed_version("初始版本", status="processed")

    response = client.put("/api/transactions/tx-1", json={"category_l1": "餐饮美食", "category_l2": "堂食正餐"})

    assert response.status_code == 400
    assert "版本" in response.get_json()["error"]


def test_manual_category_update_targets_requested_processed_version(tmp_path, monkeypatch):
    client, api_module = make_client(tmp_path, monkeypatch)
    _write_processed_fixture(api_module, [{"transaction_id": "tx-1", "counterparty": "版本一"}])
    first = api_module._save_processed_version("版本一", status="pending_tagging")
    _write_processed_fixture(api_module, [{"transaction_id": "tx-1", "counterparty": "版本二"}])
    second = api_module._save_processed_version("版本二", status="pending_tagging")

    response = client.put(
        "/api/transactions/tx-1",
        json={
            "processed_version_id": first["id"],
            "category_l1": "餐饮美食",
            "category_l2": "堂食正餐",
        },
    )
    client.post("/api/processed-versions/active", json={"id": first["id"]})
    first_tx = client.get("/api/transactions").get_json()["records"][0]
    client.post("/api/processed-versions/active", json={"id": second["id"]})
    second_tx = client.get("/api/transactions").get_json()["records"][0]
    versions = {v["id"]: v for v in client.get("/api/processed-versions").get_json()["versions"]}

    assert response.status_code == 200
    assert first_tx["category_l1"] == "餐饮美食"
    assert first_tx["category_l2"] == "堂食正餐"
    assert second_tx["category_l1"] == ""
    assert second_tx["category_l2"] == ""
    assert versions[first["id"]]["status"] == "processed"
    assert versions[first["id"]]["records"]["pending_l2"] == 0
    assert versions[second["id"]]["status"] == "pending_tagging"


def test_manual_category_update_updates_active_processed_version(tmp_path, monkeypatch):
    client, api_module = make_client(tmp_path, monkeypatch)
    _write_processed_fixture(api_module, [{"transaction_id": "tx-1"}])
    version = api_module._save_processed_version("初始版本", status="processed")

    response = client.put(
        "/api/transactions/tx-1",
        json={
            "processed_version_id": version["id"],
            "category_l1": "餐饮美食",
            "category_l2": "堂食正餐",
        },
    )
    client.post("/api/processed-versions/active", json={"id": version["id"]})
    tx = client.get("/api/transactions").get_json()["records"][0]

    assert response.status_code == 200
    assert tx["category_l1"] == "餐饮美食"
    assert tx["category_l2"] == "堂食正餐"


def test_deleting_last_active_processed_version_clears_current_dashboard_data(tmp_path, monkeypatch):
    client, api_module = make_client(tmp_path, monkeypatch)
    _write_processed_fixture(api_module, [{"transaction_id": "tx-1"}])
    version = api_module._save_processed_version("临时版本", status="processed")
    (api_module.OUTPUT_DIR / "tag_overrides.csv").write_text("transaction_id,l1,l2\n", encoding="utf-8")

    response = client.delete(f"/api/processed-versions/{version['id']}")
    summary = client.get("/api/summary")
    versions = client.get("/api/processed-versions").get_json()

    assert response.status_code == 200
    assert versions == {"active_id": "", "versions": []}
    assert summary.get_json()["total_records"] == 0
    assert not (api_module.OUTPUT_DIR / "processed_data.csv").exists()
    assert not (api_module.OUTPUT_DIR / "tag_overrides.csv").exists()


def test_run_tagging_updates_active_processed_version(tmp_path, monkeypatch):
    client, api_module = make_client(tmp_path, monkeypatch)
    _write_processed_fixture(api_module, [{"transaction_id": "tx-1"}])
    version = api_module._save_processed_version("待打标版本", status="pending_tagging")
    batch_dir = api_module.OUTPUT_DIR / "tagging_batches"
    batch_dir.mkdir(parents=True)
    (batch_dir / "manifest.json").write_text(
        json.dumps([{"file": str(batch_dir / "batch_000.txt"), "indices": [0], "count": 1}]),
        encoding="utf-8",
    )
    (batch_dir / "batch_000.txt").write_text("prompt", encoding="utf-8")

    class FakeMessages:
        def create(self, **_kwargs):
            return types.SimpleNamespace(
                content=[
                    types.SimpleNamespace(
                        type="text",
                        text=json.dumps([{"index": 1, "l1": "餐饮美食", "l2": "堂食正餐"}], ensure_ascii=False),
                    )
                ]
            )

    class FakeAnthropic:
        def __init__(self, **_kwargs):
            self.messages = FakeMessages()

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=FakeAnthropic))
    client.post(
        "/api/model-profiles",
        json={
            "name": "Fake",
            "api_key": "sk-fake",
            "base_url": "https://example.test/anthropic",
            "model": "fake-model",
            "make_active": True,
        },
    )

    response = client.post("/api/tagging/run")
    latest = None
    for _ in range(40):
        latest = client.get("/api/tagging/status").get_json()["latest_task"]
        if latest and latest["status"] not in {"queued", "running"}:
            break
        time.sleep(0.05)
    client.post("/api/processed-versions/active", json={"id": version["id"]})
    tx = client.get("/api/transactions").get_json()["records"][0]
    versions = client.get("/api/processed-versions").get_json()["versions"]

    assert response.status_code == 200
    assert latest["status"] == "completed"
    assert tx["category_l1"] == "餐饮美食"
    assert tx["category_l2"] == "堂食正餐"
    assert versions[0]["status"] == "processed"


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


def test_process_clears_stale_tagging_intermediates_before_generating_version(tmp_path, monkeypatch):
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
    batch_dir = api_module.OUTPUT_DIR / "tagging_batches"
    batch_dir.mkdir(parents=True)
    (batch_dir / "batch_999_result.json").write_text("[]", encoding="utf-8")
    (api_module.OUTPUT_DIR / "tagging_tasks.json").write_text(
        json.dumps([{"id": "stale", "status": "running"}]),
        encoding="utf-8",
    )

    def fake_pipeline(_data_dir, output_dir):
        api_module.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        fresh_batch_dir = api_module.Path(output_dir) / "tagging_batches"
        fresh_batch_dir.mkdir(parents=True, exist_ok=True)
        (fresh_batch_dir / "batch_000.txt").write_text("prompt", encoding="utf-8")
        df.to_csv(api_module.OUTPUT_DIR / "processed_data.csv", index=False, encoding="utf-8-sig")
        return df

    monkeypatch.setattr(api_module, "run_pipeline", fake_pipeline)

    response = client.post("/api/process")
    status = client.get("/api/tagging/status").get_json()

    assert response.status_code == 200
    assert status["latest_task"] is None
    assert status["batches"] == {"total": 1, "completed": 0, "pending": 1}
    assert not (batch_dir / "batch_999_result.json").exists()


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


def test_model_profile_create_new_does_not_overwrite_selected_profile(tmp_path, monkeypatch):
    client, _api_module = make_client(tmp_path, monkeypatch)

    first = client.post(
        "/api/model-profiles",
        json={
            "name": "Opus",
            "api_key": "sk-opus-secret",
            "base_url": "https://opus.example/anthropic",
            "model": "opus-model",
            "make_active": True,
        },
    )
    first_id = first.get_json()["profile"]["id"]

    second = client.post(
        "/api/model-profiles",
        json={
            "id": first_id,
            "create_new": True,
            "name": "Haiku",
            "api_key": "sk-haiku-secret",
            "base_url": "https://haiku.example/anthropic",
            "model": "haiku-model",
            "make_active": True,
        },
    )

    assert second.status_code == 200
    profiles = client.get("/api/model-profiles").get_json()
    assert len(profiles["profiles"]) == 3
    assert {"Opus", "Haiku"}.issubset({profile["name"] for profile in profiles["profiles"]})
    assert profiles["active_id"] != first_id


def test_model_profile_create_new_can_reuse_selected_key(tmp_path, monkeypatch):
    client, api_module = make_client(tmp_path, monkeypatch)

    first = client.post(
        "/api/model-profiles",
        json={
            "name": "Company Gateway",
            "api_key": "sk-shared-secret",
            "base_url": "https://gateway.example/anthropic",
            "model": "opus-model",
            "make_active": True,
        },
    )
    first_id = first.get_json()["profile"]["id"]

    response = client.post(
        "/api/model-profiles",
        json={
            "id": first_id,
            "source_profile_id": first_id,
            "create_new": True,
            "name": "Company Gateway Haiku",
            "base_url": "https://gateway.example/anthropic",
            "model": "haiku-model",
            "make_active": True,
        },
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["profile"]["api_key_configured"] is True
    assert "sk-shared-secret" not in response.get_data(as_text=True)
    assert "sk-shared-secret" in api_module.CONFIG_PATH.read_text(encoding="utf-8")
