"""
Flask REST API Server

Serves processed spending data to the frontend.
"""

import os
import json
import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS
from pathlib import Path

from .main import run_pipeline
from .classifiers.taxonomy import TAXONOMY


app = Flask(__name__)
CORS(app)

# Global DataFrame — loaded on startup
_df = None
DATA_DIR = os.environ.get("DATA_DIR", "data")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")


def _get_df() -> pd.DataFrame:
    """Get or load the processed DataFrame."""
    global _df
    if _df is None:
        csv_path = Path(OUTPUT_DIR) / "processed_data.csv"
        if csv_path.exists():
            _df = pd.read_csv(str(csv_path), encoding="utf-8-sig")
            _df["timestamp"] = pd.to_datetime(_df["timestamp"])
            _df["is_ignored"] = _df["is_ignored"].fillna(False).astype(bool)
            _df["is_refunded"] = _df["is_refunded"].fillna(False).astype(bool)
            _df["refund_amount"] = _df["refund_amount"].fillna(0).astype(float)
            _df["effective_amount"] = _df["effective_amount"].fillna(0).astype(float)
            _df["global_category_l1"] = _df["global_category_l1"].fillna("")
            _df["global_category_l2"] = _df["global_category_l2"].fillna("")
        else:
            _df = run_pipeline(DATA_DIR, OUTPUT_DIR)
    return _df


def _apply_global_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Apply global filters from query params."""
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

    # Platform filter
    platform = request.args.get("platform")
    if platform:
        df = df[df["source_platform"] == platform]

    # Track filter
    track = request.args.get("track")
    if track:
        df = df[df["track"] == track]

    # Category include (L1)
    category = request.args.get("category")
    if category:
        df = df[df["global_category_l1"] == category]

    # Category exclude (L1) — comma-separated
    exclude_cats = request.args.get("exclude_categories")
    if exclude_cats:
        excludes = [c.strip() for c in exclude_cats.split(",")]
        df = df[~df["global_category_l1"].isin(excludes)]

    # L2 category filter
    category_l2 = request.args.get("category_l2")
    if category_l2:
        df = df[df["global_category_l2"] == category_l2]

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


@app.route("/api/meta")
def meta():
    """Metadata: available users, years, categories for filter dropdowns."""
    df = _get_df()
    users = []
    for uid in df["user_id"].unique():
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

    filtered = df[mask].sort_values("timestamp", ascending=False)
    total = len(filtered)

    # Paginate
    start = (page - 1) * per_page
    page_data = filtered.iloc[start : start + per_page]

    records = []
    for _, row in page_data.iterrows():
        records.append({
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


def start_server(host="0.0.0.0", port=5001, debug=True):
    """Start the Flask dev server."""
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    start_server()
