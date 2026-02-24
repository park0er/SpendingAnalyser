"""
Meituan (美团) CSV Parser

Parses UTF-8 (BOM) CSV exported from Meituan.
File structure:
  - Variable number of metadata/disclaimer lines
  - Marker line: "【美团交易账单明细列表】"
  - Next line: column headers
  - Subsequent lines: transaction data

Special handling:
  - Amount fields have "¥" prefix that must be stripped
  - Fields are quoted with double quotes and may have trailing whitespace
  - 交易类型: 支付 / 退款 / 还款
  - File names: 美团账单(YYYYMMDD-YYYYMMDD).csv, multiple quarterly files
"""

import re
import csv
import io
import pandas as pd
from pathlib import Path
from .base import UUL_COLUMNS, create_empty_uul
from ..users import identify_user


def _strip_yen(val: str) -> float:
    """Remove ¥ prefix and parse as float."""
    val = val.strip().lstrip("¥").strip()
    try:
        return float(val)
    except ValueError:
        return 0.0


def parse_meituan(filepath: str) -> pd.DataFrame:
    """
    Parse a Meituan CSV file into UUL format.

    Args:
        filepath: Path to the Meituan CSV file

    Returns:
        DataFrame conforming to UUL schema
    """
    # Meituan exports as UTF-8 with BOM
    with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
        all_lines = f.readlines()

    # Find the marker line "【美团交易账单明细列表】"
    marker_idx = None
    for i, line in enumerate(all_lines):
        if "【美团交易账单明细列表】" in line:
            marker_idx = i
            break

    if marker_idx is None:
        raise ValueError(f"Cannot find 【美团交易账单明细列表】 marker in {filepath}")

    # Header is the line right after the marker
    header_idx = marker_idx + 1

    # User identification — default to "parko"
    user_id = "parko"

    # Join remaining lines and parse as CSV (handles quoted fields properly)
    data_text = "".join(all_lines[header_idx:])
    reader = csv.reader(io.StringIO(data_text))

    # Read header row
    try:
        header = next(reader)
        header = [h.strip() for h in header]
    except StopIteration:
        return create_empty_uul()

    records = []
    for row in reader:
        if len(row) < 11:
            continue

        # Strip all fields
        row = [cell.strip() for cell in row]

        create_time = row[0]
        success_time = row[1]
        tx_type = row[2]           # 支付 / 退款 / 还款
        order_title = row[3]
        direction = row[4]         # 支出 / 收入
        payment_method = row[5]
        order_amount = _strip_yen(row[6])
        actual_amount = _strip_yen(row[7])
        tx_id = row[8]
        merchant_order_id = row[9]
        note = row[10] if len(row) > 10 else ""

        # Use the success time as timestamp, fall back to create time
        timestamp_str = success_time if success_time else create_time
        try:
            timestamp = pd.to_datetime(timestamp_str)
        except Exception:
            continue

        # For Meituan, we use actual_amount as the primary amount
        amount = actual_amount

        # Determine if this is a refund row
        is_refund_row = (tx_type == "退款")

        # Map direction for refund rows
        if is_refund_row:
            direction_mapped = "收入"
        elif tx_type == "还款":
            direction_mapped = "不计收支"
        else:
            direction_mapped = direction

        records.append({
            "source_platform": "meituan",
            "user_id": user_id,
            "transaction_id": tx_id,
            "timestamp": timestamp,
            "direction": direction_mapped,
            "amount": amount,
            "counterparty": order_title,  # Meituan uses order title as counterparty
            "description": order_title,
            "payment_method": payment_method,
            "status": tx_type,  # Store tx_type as status (支付/退款/还款)
            "platform_category": "",  # Meituan has no category
            "platform_tx_type": tx_type,
            "original_tx_id": "",
            "merchant_order_id": merchant_order_id,
            "note": note,
            # Defaults — will be refined by downstream modules
            "track": "",
            "is_refunded": False,
            "refund_amount": 0.0,
            "effective_amount": amount,
            "is_ignored": False,  # Will be set by refund netting
            "global_category_l1": "",
            "global_category_l2": "",
        })

    if not records:
        return create_empty_uul()

    df = pd.DataFrame(records, columns=UUL_COLUMNS)
    return df
