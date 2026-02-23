"""
Main entry point — orchestrates the full pipeline:
  Parse → Refund Netting → Track Classification → Taxonomy Mapping → (LLM Tagging) → API/Report
"""

import os
import sys
import pandas as pd
from pathlib import Path

from .parsers.alipay import parse_alipay
from .parsers.wechat import parse_wechat
from .cleaners.refund_netting import apply_refund_netting
from .cleaners.non_consumption import apply_track_classification
from .classifiers.taxonomy import apply_alipay_l1_mapping
from .classifiers.llm_tagger import generate_tagging_batches


def run_pipeline(data_dir: str, output_dir: str = "output") -> pd.DataFrame:
    """
    Run the full data processing pipeline.

    Args:
        data_dir: Directory containing CSV/XLSX files
        output_dir: Directory for outputs

    Returns:
        Processed UUL DataFrame
    """
    data_path = Path(data_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Parse ────────────────────────────────────────────
    print("📂 Step 1: Parsing data files...")

    dfs = []

    # Alipay CSV files
    for f in sorted(data_path.glob("支付宝*.csv")):
        print(f"  → Alipay: {f.name}")
        df = parse_alipay(str(f))
        print(f"    {len(df)} records parsed")
        dfs.append(df)

    # WeChat XLSX files
    wechat_files = list(data_path.glob("微信支付*.xlsx"))
    if wechat_files:
        print(f"  → WeChat: {len(wechat_files)} quarterly files")
        df = parse_wechat(str(data_path))
        print(f"    {len(df)} records parsed")
        dfs.append(df)

    if not dfs:
        print("❌ No data files found in", data_dir)
        return pd.DataFrame()

    all_data = pd.concat(dfs, ignore_index=True)
    print(f"  ✅ Total: {len(all_data)} records from {len(dfs)} source(s)")

    # ── Step 2: Refund Netting ───────────────────────────────────
    print("\n💰 Step 2: Refund netting...")
    all_data = apply_refund_netting(all_data)

    refunded = all_data[all_data["is_refunded"]].shape[0]
    ignored = all_data[all_data["is_ignored"]].shape[0]
    print(f"  ✅ {refunded} records have refunds, {ignored} refund rows ignored")

    # ── Step 3: Track Classification ─────────────────────────────
    print("\n🔀 Step 3: Track classification (consumption vs cashflow)...")
    all_data = apply_track_classification(all_data)

    consumption = all_data[all_data["track"] == "consumption"].shape[0]
    cashflow = all_data[all_data["track"] == "cashflow"].shape[0]
    print(f"  ✅ Consumption: {consumption} | Cashflow: {cashflow}")

    # ── Step 4: Taxonomy Mapping ─────────────────────────────────
    print("\n🏷️  Step 4: Taxonomy mapping (L1)...")
    all_data = apply_alipay_l1_mapping(all_data)

    with_l1 = all_data[all_data["global_category_l1"] != ""].shape[0]
    print(f"  ✅ {with_l1} records have L1 category")

    # ── Step 5: Generate LLM Tagging Batches ─────────────────────
    tagging_dir = str(output_path / "tagging_batches")
    print(f"\n🤖 Step 5: Generating LLM tagging batches...")
    batches = generate_tagging_batches(all_data, tagging_dir)
    print(f"  ✅ {len(batches)} batch files generated in {tagging_dir}")

    # ── Step 6: Save processed data ──────────────────────────────
    # Save as CSV for inspection
    data_file = output_path / "processed_data.csv"
    all_data.to_csv(str(data_file), index=False, encoding="utf-8-sig")
    print(f"\n💾 Processed data saved to {data_file}")

    # ── Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📊 PIPELINE SUMMARY")
    print("=" * 60)

    # Consumption track stats
    consumption_df = all_data[
        (all_data["track"] == "consumption") & (~all_data["is_ignored"])
    ]
    total_spend = consumption_df["effective_amount"].sum()
    print(f"\n🛒 Consumption Track:")
    print(f"   Records:  {len(consumption_df)}")
    print(f"   Total:    ¥{total_spend:,.2f}")

    # By L1 category
    if not consumption_df["global_category_l1"].empty:
        print(f"\n   By L1 Category:")
        l1_summary = (
            consumption_df.groupby("global_category_l1")["effective_amount"]
            .agg(["sum", "count"])
            .sort_values("sum", ascending=False)
        )
        for cat, row in l1_summary.iterrows():
            if cat:
                pct = row["sum"] / total_spend * 100 if total_spend > 0 else 0
                print(f"     {cat:12s}  ¥{row['sum']:>10,.2f}  ({row['count']:>3.0f}笔, {pct:>5.1f}%)")

    # Cashflow track stats
    cashflow_df = all_data[all_data["track"] == "cashflow"]
    print(f"\n💸 Cashflow Track:")
    print(f"   Records:  {len(cashflow_df)}")

    # By platform
    print(f"\n📱 By Platform:")
    for platform in all_data["source_platform"].unique():
        p_df = all_data[all_data["source_platform"] == platform]
        p_cons = p_df[p_df["track"] == "consumption"]
        print(f"   {platform}: {len(p_df)} total, {len(p_cons)} consumption")

    # Pending LLM tagging
    needs_l2 = consumption_df[consumption_df["global_category_l2"].fillna("") == ""]
    print(f"\n⏳ Awaiting LLM L2 tagging: {len(needs_l2)} records ({len(batches)} batches)")

    return all_data


if __name__ == "__main__":
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "data"
    run_pipeline(data_dir)
