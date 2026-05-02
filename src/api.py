"""
Flask REST API Server

Serves processed spending data to the frontend.
"""

import os
import re
import pandas as pd
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from pathlib import Path
from werkzeug.utils import secure_filename

from .main import run_pipeline
from .parsers.base import create_empty_uul
from .classifiers.taxonomy import TAXONOMY


FRONTEND_DIR_RAW = os.environ.get("FRONTEND_DIR", "")
FRONTEND_DIR = Path(FRONTEND_DIR_RAW).resolve() if FRONTEND_DIR_RAW else None

app = Flask(
    __name__,
    static_folder=str(FRONTEND_DIR) if FRONTEND_DIR else None,
    static_url_path="",
)
CORS(app)

# Global DataFrame — loaded on startup
_df = None
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "output"))
CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", "config.env"))

PLATFORM_LABELS = {
    "alipay": "支付宝",
    "wechat": "微信支付",
    "jd": "京东交易流水",
    "meituan": "美团账单",
}

ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def _empty_df() -> pd.DataFrame:
    df = create_empty_uul()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def _normalise_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure API consumers can rely on the full UUL schema and dtypes."""
    if df is None or df.empty:
        return _empty_df()

    empty = _empty_df()
    for col in empty.columns:
        if col not in df.columns:
            df[col] = empty[col]

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["is_ignored"] = df["is_ignored"].fillna(False).astype(bool)
    df["is_refunded"] = df["is_refunded"].fillna(False).astype(bool)
    df["refund_amount"] = df["refund_amount"].fillna(0).astype(float)
    df["effective_amount"] = df["effective_amount"].fillna(0).astype(float)
    df["amount"] = df["amount"].fillna(0).astype(float)

    text_cols = [
        "source_platform",
        "user_id",
        "transaction_id",
        "direction",
        "counterparty",
        "description",
        "payment_method",
        "status",
        "platform_category",
        "platform_tx_type",
        "original_tx_id",
        "merchant_order_id",
        "note",
        "track",
        "global_category_l1",
        "global_category_l2",
    ]
    for col in text_cols:
        df[col] = df[col].fillna("")

    return df


def _get_df() -> pd.DataFrame:
    """Get or load the processed DataFrame."""
    global _df
    if _df is None:
        csv_path = OUTPUT_DIR / "processed_data.csv"
        if csv_path.exists():
            _df = _normalise_df(pd.read_csv(str(csv_path), encoding="utf-8-sig"))
        else:
            _df = _normalise_df(run_pipeline(str(DATA_DIR), str(OUTPUT_DIR)))
    return _df


def _apply_global_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Apply global filters from query params."""
    if df.empty:
        return df

    # User filter
    user = request.args.get("user")
    if user:
        df = df[df["user_id"] == user]

    # Year filter
    year = request.args.get("year")
    if year:
        df = df[df["timestamp"].dt.year == int(year)]

    # Date range filter
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    if date_from:
        df = df[df["timestamp"] >= pd.to_datetime(date_from)]
    if date_to:
        df = df[df["timestamp"] <= pd.to_datetime(date_to + " 23:59:59")]

    # Platform filter (supports comma-separated multi-select)
    platform = request.args.get("platform")
    if platform:
        platforms = [p.strip() for p in platform.split(",")]
        df = df[df["source_platform"].isin(platforms)]

    # Track filter
    track = request.args.get("track")
    if track:
        df = df[df["track"] == track]

    # Category include (L1, supports comma-separated multi-select)
    category = request.args.get("category")
    if category:
        categories = [c.strip() for c in category.split(",")]
        df = df[df["global_category_l1"].isin(categories)]

    # Category exclude (L1 or L2) — comma-separated
    exclude_cats = request.args.get("exclude_categories")
    if exclude_cats:
        excludes = [c.strip() for c in exclude_cats.split(",")]
        df = df[
            (~df["global_category_l1"].isin(excludes)) & 
            (~df["global_category_l2"].isin(excludes))
        ]

    # L2 category filter (supports comma-separated multi-select)
    category_l2 = request.args.get("category_l2")
    if category_l2:
        l2s = [c.strip() for c in category_l2.split(",")]
        df = df[df["global_category_l2"].isin(l2s)]

    return df


def _consumption_df(df: pd.DataFrame = None) -> pd.DataFrame:
    """Get consumption-track records only."""
    if df is None:
        df = _get_df()
    return df[(df["track"] == "consumption") & (~df["is_ignored"])]


def _cashflow_df(df: pd.DataFrame = None) -> pd.DataFrame:
    """Get cashflow-track records."""
    if df is None:
        df = _get_df()
    return df[df["track"] == "cashflow"]


def _read_config() -> dict:
    config = {
        "LLM_API_KEY": "",
        "LLM_BASE_URL": "https://api.xiaomimimo.com/anthropic",
        "LLM_MODEL": "mimo-v2.5-pro",
    }
    if CONFIG_PATH.exists():
        for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                config[key.strip()] = value.strip()
    return config


def _write_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        "\n".join([
            "# SpendingAnalyser LLM 配置",
            "# 这个文件由桌面 App 的模型配置面板自动维护。",
            f"LLM_API_KEY={config.get('LLM_API_KEY', '')}",
            f"LLM_BASE_URL={config.get('LLM_BASE_URL', '')}",
            f"LLM_MODEL={config.get('LLM_MODEL', '')}",
            "",
        ]),
        encoding="utf-8",
    )


def _has_real_api_key(value: str) -> bool:
    if not value:
        return False
    lowered = value.lower()
    return not any(token in lowered for token in ["your_key", "api密钥", "在此填写"])


def _safe_upload_name(platform: str, original_name: str) -> str:
    clean_original = Path(original_name).name
    ext = Path(clean_original).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError("仅支持 CSV、XLSX、XLS 文件")

    label = PLATFORM_LABELS[platform]
    stem = Path(clean_original).stem
    if stem.startswith(label):
        return f"{stem}{ext}"

    safe_stem = secure_filename(stem) or "bill"
    safe_stem = re.sub(r"[-\s]+", "_", safe_stem).strip("_")
    return f"{label}_{safe_stem}{ext}"


def _safe_user_id(raw_user: str) -> str:
    user_id = (raw_user or "").strip()
    if not user_id:
        raise ValueError("请填写账单归属用户")

    user_id = re.sub(r"[\r\n\t]+", " ", user_id)
    user_id = re.sub(r"[\\/:\0]+", "-", user_id)
    user_id = re.sub(r"\s+", " ", user_id).strip(" .")
    if not user_id or user_id in {".", ".."}:
        raise ValueError("用户名不合法")
    if len(user_id) > 40:
        raise ValueError("用户名最多 40 个字符")
    return user_id


def _detect_platform(filename: str) -> str:
    for key, label in PLATFORM_LABELS.items():
        if filename.startswith(label):
            return key
    return ""


def _iter_upload_files():
    if not DATA_DIR.exists():
        return

    for path in sorted(DATA_DIR.glob("*")):
        if path.is_file() and path.suffix.lower() in ALLOWED_UPLOAD_EXTENSIONS:
            yield path, ""

    for user_dir in sorted(p for p in DATA_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")):
        for path in sorted(user_dir.glob("*")):
            if path.is_file() and path.suffix.lower() in ALLOWED_UPLOAD_EXTENSIONS:
                yield path, user_dir.name


def _uploaded_user_ids() -> list[str]:
    return sorted({user_id for _, user_id in _iter_upload_files() if user_id})


def _upload_file_payload(path: Path, user_id: str) -> dict:
    return {
        "name": path.name,
        "relative_path": str(path.relative_to(DATA_DIR)),
        "platform": _detect_platform(path.name),
        "user": user_id,
        "size": path.stat().st_size,
    }


@app.route("/api/health")
def health():
    return jsonify({"ok": True})


@app.route("/api/config", methods=["GET", "POST"])
def config():
    current = _read_config()

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        api_key = data.get("api_key")
        if api_key:
            current["LLM_API_KEY"] = api_key.strip()
        current["LLM_BASE_URL"] = data.get("base_url", current["LLM_BASE_URL"]).strip()
        current["LLM_MODEL"] = data.get("model", current["LLM_MODEL"]).strip()
        _write_config(current)

    return jsonify({
        "api_key_configured": _has_real_api_key(current.get("LLM_API_KEY", "")),
        "base_url": current.get("LLM_BASE_URL", ""),
        "model": current.get("LLM_MODEL", ""),
    })


@app.route("/api/uploads", methods=["GET", "POST"])
def uploads():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if request.method == "POST":
        platform = request.form.get("platform", "")
        if platform not in PLATFORM_LABELS:
            return jsonify({"error": "请选择账单渠道"}), 400

        try:
            user_id = _safe_user_id(request.form.get("user", ""))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        incoming_files = request.files.getlist("files")
        if not incoming_files:
            return jsonify({"error": "请选择要上传的账单文件"}), 400

        user_dir = DATA_DIR / user_id
        user_dir.mkdir(parents=True, exist_ok=True)

        saved_files = []
        for incoming in incoming_files:
            if not incoming.filename:
                continue
            try:
                filename = _safe_upload_name(platform, incoming.filename)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

            target = user_dir / filename
            counter = 1
            while target.exists():
                target = user_dir / f"{Path(filename).stem}_{counter}{Path(filename).suffix}"
                counter += 1
            incoming.save(target)
            saved_files.append(_upload_file_payload(target, user_id))

        return jsonify({"files": saved_files})

    files = [_upload_file_payload(path, user_id) for path, user_id in _iter_upload_files()]
    return jsonify({"files": files})


@app.route("/api/process", methods=["POST"])
def process_data():
    global _df
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _df = _normalise_df(run_pipeline(str(DATA_DIR), str(OUTPUT_DIR)))
    return jsonify({
        "success": True,
        "has_data": not _df.empty,
        "total_records": int(len(_df)),
        "users": sorted([u for u in _df["user_id"].unique().tolist() if u]),
    })


@app.route("/api/meta")
def meta():
    """Metadata: available users, years, categories for filter dropdowns."""
    csv_path = OUTPUT_DIR / "processed_data.csv"
    df = _get_df() if (_df is not None or csv_path.exists()) else _empty_df()
    users = []
    user_ids = sorted(set([u for u in df["user_id"].unique().tolist() if u]) | set(_uploaded_user_ids()))
    for uid in user_ids:
        users.append({"id": uid, "label": uid})

    years = sorted(df["timestamp"].dt.year.unique().tolist(), reverse=True)

    platforms = df["source_platform"].unique().tolist()

    # L1+L2 taxonomy
    taxonomy = []
    for l1, l2s in TAXONOMY.items():
        # Check if any records actually have this L1
        count = len(df[df["global_category_l1"] == l1])
        taxonomy.append({"l1": l1, "l2s": l2s, "count": count})

    return jsonify({
        "users": users,
        "years": years,
        "platforms": platforms,
        "taxonomy": taxonomy,
    })


@app.route("/api/summary")
def summary():
    """Overall summary stats (respects global filters)."""
    df = _apply_global_filters(_get_df())
    cons = _consumption_df(df)
    cash = _cashflow_df(df)

    total_spend = cons["effective_amount"].sum()
    total_refund = df[df["is_refunded"]]["refund_amount"].sum()
    cashflow_total = cash[cash["direction"] == "支出"]["amount"].sum()

    return jsonify({
        "total_records": len(df),
        "consumption_records": len(cons),
        "cashflow_records": len(cash),
        "total_spend": round(total_spend, 2),
        "total_refund": round(total_refund, 2),
        "cashflow_total": round(cashflow_total, 2),
        "platforms": {
            p: int(c) for p, c in df["source_platform"].value_counts().items()
        },
    })


@app.route("/api/by-category")
def by_category():
    """Spending aggregated by L1 (and optionally L2) category."""
    df = _apply_global_filters(_get_df())
    cons = _consumption_df(df)
    level = request.args.get("level", "l1")

    if level == "l2":
        group_col = ["global_category_l1", "global_category_l2"]
    else:
        group_col = ["global_category_l1"]

    if cons.empty:
        return jsonify([])

    result = (
        cons.groupby(group_col)["effective_amount"]
        .agg(["sum", "count"])
        .reset_index()
    )
    result.columns = [*group_col, "total", "count"]
    result = result.sort_values("total", ascending=False)
    result["total"] = result["total"].round(2)

    return jsonify(result.to_dict(orient="records"))


@app.route("/api/by-period")
def by_period():
    """Spending over time, grouped by period."""
    df = _apply_global_filters(_get_df())
    cons = _consumption_df(df).copy()
    granularity = request.args.get("granularity", "month")

    if cons.empty:
        return jsonify([])

    if granularity == "year":
        cons["period"] = cons["timestamp"].dt.strftime("%Y")
    elif granularity == "week":
        cons["period"] = cons["timestamp"].dt.strftime("%Y-W%W")
    else:
        cons["period"] = cons["timestamp"].dt.strftime("%Y-%m")

    result = (
        cons.groupby("period")["effective_amount"]
        .agg(["sum", "count"])
        .reset_index()
    )
    result.columns = ["period", "total", "count"]
    result = result.sort_values("period")
    result["total"] = result["total"].round(2)

    return jsonify(result.to_dict(orient="records"))


@app.route("/api/top-merchants")
def top_merchants():
    """Top spending merchants."""
    df = _apply_global_filters(_get_df())
    cons = _consumption_df(df)
    limit = int(request.args.get("limit", 15))

    if cons.empty:
        return jsonify([])

    result = (
        cons.groupby("counterparty")["effective_amount"]
        .agg(["sum", "count"])
        .reset_index()
    )
    result.columns = ["merchant", "total", "count"]
    result = result.sort_values("total", ascending=False).head(limit)
    result["total"] = result["total"].round(2)

    return jsonify(result.to_dict(orient="records"))


@app.route("/api/top-categories")
def top_categories():
    """Top spending categories with amount totals."""
    df = _apply_global_filters(_get_df())
    cons = _consumption_df(df)
    level = request.args.get("level", "l1")
    limit = int(request.args.get("limit", 20))

    if cons.empty:
        return jsonify([])

    if level == "l2":
        group_col = ["global_category_l1", "global_category_l2"]
    else:
        group_col = ["global_category_l1"]

    result = (
        cons.groupby(group_col)["effective_amount"]
        .agg(["sum", "count", "mean"])
        .reset_index()
    )
    if level == "l2":
        result.columns = ["category_l1", "category_l2", "total", "count", "avg"]
    else:
        result.columns = ["category", "total", "count", "avg"]

    result = result.sort_values("total", ascending=False).head(limit)
    result["total"] = result["total"].round(2)
    result["avg"] = result["avg"].round(2)

    return jsonify(result.to_dict(orient="records"))


@app.route("/api/cashflow-summary")
def cashflow_summary():
    """Cashflow track summary."""
    df = _apply_global_filters(_get_df())
    cash = _cashflow_df(df)

    categories = {}
    for _, row in cash.iterrows():
        cat = row["platform_category"] or row["platform_tx_type"] or "其他"
        if cat not in categories:
            categories[cat] = {"total": 0, "count": 0}
        categories[cat]["total"] += row["amount"]
        categories[cat]["count"] += 1

    result = [
        {"category": k, "total": round(v["total"], 2), "count": v["count"]}
        for k, v in sorted(categories.items(), key=lambda x: -x[1]["total"])
    ]

    return jsonify({
        "total_records": len(cash),
        "categories": result,
    })


@app.route("/api/transactions")
def transactions():
    """Transaction list with pagination and filtering."""
    df = _apply_global_filters(_get_df())

    # Additional transaction-specific filters
    search = request.args.get("search", "")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))

    # Don't filter by is_ignored by default — show all
    mask = pd.Series(True, index=df.index)

    if search:
        search_mask = (
            df["counterparty"].str.contains(search, case=False, na=False)
            | df["description"].str.contains(search, case=False, na=False)
        )
        mask &= search_mask

    # Server-side sorting
    sort_by = request.args.get("sort_by", "timestamp")
    sort_order = request.args.get("sort_order", "desc")
    sort_col_map = {
        "timestamp": "timestamp",
        "amount": "amount",
        "effective_amount": "effective_amount",
        "counterparty": "counterparty",
        "platform": "source_platform",
        "category_l1": "global_category_l1",
        "category_l2": "global_category_l2",
        "track": "track",
        "payment_method": "payment_method",
    }
    sort_column = sort_col_map.get(sort_by, "timestamp")
    ascending = sort_order != "desc"
    filtered = df[mask].sort_values(sort_column, ascending=ascending, na_position="last")
    total = len(filtered)

    # Paginate
    start = (page - 1) * per_page
    page_data = filtered.iloc[start : start + per_page]

    records = []
    for _, row in page_data.iterrows():
        records.append({
            "id": row["transaction_id"],
            "timestamp": str(row["timestamp"]),
            "platform": row["source_platform"],
            "user_id": row["user_id"],
            "counterparty": row["counterparty"],
            "description": row["description"],
            "amount": round(float(row["amount"]), 2),
            "effective_amount": round(float(row["effective_amount"]), 2),
            "direction": row["direction"],
            "category_l1": row["global_category_l1"] or "",
            "category_l2": row["global_category_l2"] or "",
            "payment_method": row["payment_method"],
            "track": row["track"],
            "is_refunded": bool(row["is_refunded"]),
            "is_ignored": bool(row["is_ignored"]),
        })

    return jsonify({
        "total": total,
        "page": page,
        "per_page": per_page,
        "records": records,
    })


@app.route("/api/transactions/<path:tx_id>", methods=["PUT"])
def update_transaction(tx_id):
    """Update a transaction's L1 and L2 categories."""
    df = _get_df()
    data = request.json
    
    if "category_l1" not in data or "category_l2" not in data:
        return jsonify({"error": "Missing category data"}), 400
        
    l1 = data["category_l1"]
    l2 = data["category_l2"]
    
    # Find the record by transaction_id
    mask = df["transaction_id"] == tx_id
    if not mask.any():
        return jsonify({"error": "Transaction not found"}), 404
        
    df.loc[mask, "global_category_l1"] = l1
    df.loc[mask, "global_category_l2"] = l2
    
    # Save back to CSV
    csv_path = Path(OUTPUT_DIR) / "processed_data.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    
    return jsonify({"success": True})


def start_server(host="0.0.0.0", port=5001, debug=True):
    """Start the Flask dev server."""
    app.run(host=host, port=port, debug=debug)


@app.route("/")
@app.route("/<path:path>")
def frontend_app(path="index.html"):
    """Serve the built dashboard when packaged as a desktop app."""
    if not FRONTEND_DIR:
        return jsonify({"error": "Frontend build directory is not configured"}), 404

    requested = FRONTEND_DIR / path
    if requested.exists() and requested.is_file():
        return send_from_directory(str(FRONTEND_DIR), path)
    return send_from_directory(str(FRONTEND_DIR), "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))
    debug = os.environ.get("SPENDING_DESKTOP") != "1"
    start_server(port=port, debug=debug)
